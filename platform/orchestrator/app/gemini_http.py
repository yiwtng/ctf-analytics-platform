"""
Shared Gemini REST helper: retry on 429/503 with Retry-After + exponential backoff.
"""

from __future__ import annotations

import os
import random
import time
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

GEMINI_MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "8"))
GEMINI_RETRY_BASE_SECONDS = float(os.getenv("GEMINI_RETRY_BASE_SECONDS", "3"))
GEMINI_RETRY_MAX_SLEEP = float(os.getenv("GEMINI_RETRY_MAX_SLEEP_SECONDS", "120"))
GEMINI_PER_MODEL_MAX_RETRIES = int(os.getenv("GEMINI_PER_MODEL_MAX_RETRIES", "4"))
GEMINI_MODEL_SWITCH_GAP_SECONDS = float(os.getenv("GEMINI_MODEL_SWITCH_GAP_SECONDS", "0.5"))

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def parse_retry_after_seconds(resp: requests.Response) -> Optional[float]:
    header = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
    if not header:
        return None
    header = header.strip()
    try:
        return float(header)
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(header)
        if dt is None:
            return None
        return max(0.0, dt.timestamp() - time.time())
    except Exception:
        return None


def post_generate_content(
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    timeout: float = 60,
    max_retries: Optional[int] = None,
) -> requests.Response:
    """
    POST to Gemini generateContent. Retries on HTTP 429 and 503.

    Returns the final Response (may still be 429 if all retries exhausted).
    Raises HTTPError for other non-success status codes after retries logic.
    """
    attempts = max_retries if max_retries is not None else GEMINI_MAX_RETRIES
    last: Optional[requests.Response] = None

    for attempt in range(attempts):
        last = requests.post(url, params=params, json=json_body, timeout=timeout)
        if last.status_code == 200:
            return last

        # Wrong model id or bad payload — no point retrying the same URL
        if last.status_code in (400, 404):
            return last

        if last.status_code in (429, 503) and attempt < attempts - 1:
            wait = parse_retry_after_seconds(last)
            if wait is None:
                wait = min(
                    GEMINI_RETRY_MAX_SLEEP,
                    GEMINI_RETRY_BASE_SECONDS * (2**attempt) * random.uniform(0.85, 1.15),
                )
            else:
                wait = min(GEMINI_RETRY_MAX_SLEEP, max(0.0, wait))
            time.sleep(wait)
            continue

        # Return any final status (5xx, exhausted 429/503, etc.) — callers rotate models or fallback
        return last

    if last is not None:
        return last
    raise RuntimeError("Gemini request failed without response")


def parse_gemini_models() -> List[str]:
    """
    Comma-separated GEMINI_MODELS, or single GEMINI_MODEL if unset.
    Example: gemini-2.5-flash,gemini-2.5-flash-lite,gemini-1.5-flash-8b
    """
    raw = os.getenv("GEMINI_MODELS", "").strip()
    if raw:
        return [m.strip() for m in raw.split(",") if m.strip()]
    single = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    return [single] if single else []


def post_generate_content_first_available(
    *,
    api_key: str,
    json_body: Dict[str, Any],
    models: List[str],
    timeout: float = 60,
) -> Tuple[Optional[requests.Response], str]:
    """
    Try models in order until one returns HTTP 200 (after per-model retries).
    When multiple models are configured, use fewer retries per model so we
    rotate before burning one quota bucket.

    Returns (response, model_used). On total failure, response may be last
    non-200 (e.g. 429) and model_used is the last model tried.
    """
    if not models:
        return None, ""

    per_model_retries = GEMINI_MAX_RETRIES
    if len(models) > 1:
        per_model_retries = min(GEMINI_MAX_RETRIES, GEMINI_PER_MODEL_MAX_RETRIES)

    last: Optional[requests.Response] = None
    last_model = ""
    for idx, model in enumerate(models):
        url = f"{GEMINI_API_BASE.format(model=model)}?key={api_key}"
        last = post_generate_content(
            url,
            json_body=json_body,
            timeout=timeout,
            max_retries=per_model_retries,
        )
        last_model = model
        if last.status_code == 200:
            return last, model
        if idx < len(models) - 1 and GEMINI_MODEL_SWITCH_GAP_SECONDS > 0:
            time.sleep(GEMINI_MODEL_SWITCH_GAP_SECONDS)

    return last, last_model
