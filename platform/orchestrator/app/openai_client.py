"""
OpenAI Chat Completions for JSON-shaped coaching reports (alternative to Gemini).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from openai import APIError, OpenAI, RateLimitError

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"


def preferred_ai_backend() -> str:
    """
    Which backend to use for player reports when both keys may exist.
    AI_PROVIDER=openai|gemini forces; empty = prefer OpenAI if OPENAI_API_KEY set.
    """
    raw = os.getenv("AI_PROVIDER", "").strip().lower()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()

    if raw == "openai":
        return "openai" if openai_key else ("gemini" if gemini_key else "none")
    if raw == "gemini":
        return "gemini" if gemini_key else ("openai" if openai_key else "none")
    if openai_key:
        return "openai"
    if gemini_key:
        return "gemini"
    return "none"


def available_ai_backends() -> List[str]:
    """
    Ordered list of usable AI backends.
    The configured provider is treated as preferred, but the other available
    provider remains eligible as a fallback when the preferred one is limited.
    """
    raw = os.getenv("AI_PROVIDER", "").strip().lower()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()

    preferred_order = ["openai", "gemini"]
    if raw == "gemini":
        preferred_order = ["gemini", "openai"]
    elif raw == "openai":
        preferred_order = ["openai", "gemini"]

    available: List[str] = []
    for backend in preferred_order:
        if backend == "openai" and openai_key and backend not in available:
            available.append(backend)
        elif backend == "gemini" and gemini_key and backend not in available:
            available.append(backend)

    return available


def chat_json_object(
    *,
    prompt: str,
    api_key: str,
    model: Optional[str] = None,
    timeout: float = 120.0,
) -> Tuple[Optional[Dict[str, Any]], str, Optional[str]]:
    """
    Returns (parsed_json_or_none, model_used, error_tag).
    error_tag is short: 'rate_limit', 'timeout', 'api', 'json', or freeform.
    """
    m = (model or OPENAI_MODEL).strip()
    client = OpenAI(api_key=api_key, timeout=timeout)
    try:
        resp = client.chat.completions.create(
            model=m,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
    except RateLimitError as e:
        return None, m, f"rate_limit:{e}"
    except APIError as e:
        err_name = type(e).__name__
        if "Timeout" in err_name or "timeout" in str(e).lower():
            return None, m, f"timeout:{e}"
        return None, m, f"api:{e}"
    except Exception as e:
        return None, m, str(e)

    text = (resp.choices[0].message.content or "").strip()
    try:
        return json.loads(text), m, None
    except json.JSONDecodeError as e:
        return None, m, f"json:{e}"
