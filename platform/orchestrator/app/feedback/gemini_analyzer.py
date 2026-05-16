import json
import os
from typing import Any

import requests
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import SessionLocal
from app.events import write_ai_report
from app.gemini_http import parse_gemini_models, post_generate_content_first_available
from app.openai_client import available_ai_backends, chat_json_object


class AIReport(BaseModel):
    profile: list[str] = Field(description="Behavior profile labels for the player.")
    strengths: list[str] = Field(description="Observed strengths from the event summaries.")
    weaknesses: list[str] = Field(description="Observed weaknesses from the event summaries.")
    recommendations: list[str] = Field(description="Actionable post-competition recommendations.")
    summary: str = Field(description="Short overall summary in Thai.")
    confidence: str = Field(description="low, medium, or high")


PLAYER_EVENTS = {
    "WEB_REQUEST",
    "TCP_INPUT",
    "TCP_HELLO_OK",
    "TCP_AUTH_ATTEMPT",
    "TCP_BAD_AUTH",
    "TCP_MALFORMED",
    "FLAG_FOUND",
    "SSH_COMMAND",
    "SSH_FLAG_ATTEMPT",
}

def _fetch_user_event_summary(user_key: str) -> dict[str, Any]:
    with SessionLocal() as db:
        events = db.execute(
            text("""
                SELECT challenge_id, event_type, COUNT(*) AS cnt
                FROM events
                WHERE user_key = :user_key
                  AND event_type = ANY(:event_types)
                GROUP BY challenge_id, event_type
                ORDER BY challenge_id, event_type
            """),
            {
                "user_key": user_key,
                "event_types": list(PLAYER_EVENTS),
            },
        ).mappings().all()

        feedbacks = db.execute(
            text("""
                SELECT challenge_id, feedback_type, severity, COUNT(*) AS cnt
                FROM feedback_reports
                WHERE user_key = :user_key
                GROUP BY challenge_id, feedback_type, severity
                ORDER BY challenge_id, feedback_type
            """),
            {"user_key": user_key},
        ).mappings().all()

    by_challenge: dict[str, dict[str, int]] = {}
    for row in events:
        by_challenge.setdefault(row["challenge_id"], {})
        by_challenge[row["challenge_id"]][row["event_type"]] = row["cnt"]

    feedback_summary: dict[str, list[dict[str, Any]]] = {}
    for row in feedbacks:
        feedback_summary.setdefault(row["challenge_id"], [])
        feedback_summary[row["challenge_id"]].append(
            {
                "feedback_type": row["feedback_type"],
                "severity": row["severity"],
                "count": row["cnt"],
            }
        )

    challenge_summaries = []

    for challenge_id, counters in by_challenge.items():
        obs: dict[str, Any] = {}

        if challenge_id == "red_ghost_login":
            obs["category"] = "web"
            obs["web_requests"] = counters.get("WEB_REQUEST", 0)

        elif challenge_id == "red_protocol_probe":
            obs["category"] = "nc"
            obs["tcp_inputs"] = counters.get("TCP_INPUT", 0)
            obs["hello_ok"] = counters.get("TCP_HELLO_OK", 0) > 0
            obs["bad_auth_count"] = counters.get("TCP_BAD_AUTH", 0)
            obs["malformed_count"] = counters.get("TCP_MALFORMED", 0)
            obs["flag_found"] = counters.get("FLAG_FOUND", 0) > 0
            obs["auth_attempt_count"] = counters.get("TCP_AUTH_ATTEMPT", 0)

        elif challenge_id == "red_pivot_notes":
            obs["category"] = "ssh"
            obs["ssh_command_count"] = counters.get("SSH_COMMAND", 0)
            obs["ssh_flag_attempt"] = counters.get("SSH_FLAG_ATTEMPT", 0) > 0

        for item in feedback_summary.get(challenge_id, []):
            if item["feedback_type"] != "general":
                obs[item["feedback_type"]] = True

        challenge_summaries.append({
            "challenge_id": challenge_id,
            "observations": obs
        })

    return {
        "user_key": user_key,
        "challenge_summaries": challenge_summaries
    }


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return [str(value).strip()]


def _pick_first(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return None


def _normalize_confidence(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"low", "medium", "high"}:
        return text
    if "high" in text or "สูง" in text:
        return "high"
    if "low" in text or "ต่ำ" in text:
        return "low"
    return "medium"


def _normalize_ai_payload(payload: Any) -> AIReport:
    if isinstance(payload, list):
        payload = payload[0] if payload else {}

    if isinstance(payload, str):
        return AIReport(
            profile=["วิเคราะห์จากข้อมูลกิจกรรมที่มีอยู่"],
            strengths=[],
            weaknesses=[],
            recommendations=["ตรวจสอบรูปแบบผลลัพธ์จาก Gemini เพิ่มเติม"],
            summary=payload[:1000],
            confidence="low",
        )

    if not isinstance(payload, dict):
        raise ValueError("Gemini payload is not a dict or list")

    report_root = payload
    if isinstance(payload.get("analysis"), dict):
        report_root = payload["analysis"]

    profile = _as_string_list(_pick_first(
        report_root,
        "profile",
        "profiles",
        "player_profile",
        "behavior_profile",
        "analysis_profile",
    ))
    strengths = _as_string_list(_pick_first(
        report_root,
        "strengths",
        "key_strengths",
        "observed_strengths",
    ))
    weaknesses = _as_string_list(_pick_first(
        report_root,
        "weaknesses",
        "areas_for_improvement",
        "weak_points",
    ))
    recommendations = _as_string_list(_pick_first(
        report_root,
        "recommendations",
        "action_items",
        "suggested_actions",
        "next_steps",
    ))
    summary = str(_pick_first(
        report_root,
        "summary",
        "analysis",
        "overall_summary",
        "analysis_summary",
        "ai_summary",
    ) or json.dumps(payload, ensure_ascii=False)[:1000]).strip()
    confidence = _normalize_confidence(_pick_first(
        report_root,
        "confidence",
        "confidence_level",
        "confidenceLevel",
    ))

    if not profile:
        profile = ["วิเคราะห์จากข้อมูลกิจกรรมที่มีอยู่"]
    if not recommendations:
        recommendations = ["ควรตรวจสอบผลลัพธ์จาก Gemini เพิ่มเติมก่อนนำไปใช้แบบอัตโนมัติ"]

    return AIReport(
        profile=profile,
        strengths=strengths,
        weaknesses=weaknesses,
        recommendations=recommendations,
        summary=summary,
        confidence=confidence,
    )


def _extract_ai_report(raw: dict[str, Any]) -> AIReport:
    text = ""
    candidates = raw.get("candidates", [])
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        if parts:
            text = parts[0].get("text", "")

    parsed = json.loads(text)
    return _normalize_ai_payload(parsed)


def analyze_user_with_gemini(user_key: str) -> dict[str, Any]:
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    backends = available_ai_backends()

    if not backends:
        return {
            "status": "error",
            "message": "No AI backend is configured",
            "user_key": user_key,
        }

    summary = _fetch_user_event_summary(user_key)
    prompt = f"""
คุณเป็น cyber training analyst
นี่คือข้อมูลสรุปหลังการแข่งขันของผู้เล่น 1 คน

ข้อมูล:
{summary}

กติกา:
1. วิเคราะห์จาก challenge_summaries เท่านั้น
2. ห้ามตีความ event ภายในระบบที่ไม่อยู่ใน summary ว่าเป็นพฤติกรรมผู้เล่น
3. ห้ามสรุปว่าผู้เล่นพึ่งพาคำใบ้ ถ้าไม่มีข้อมูล hint จริง
4. ถ้าข้อมูลยังไม่พอ ให้ใช้ confidence ระดับ low หรือ medium
5. เขียนภาษาไทย กระชับ ชัดเจน
6. recommendations ต้อง actionable และเป็น post-competition feedback
7. ส่งออกเป็น JSON ตาม schema: profile (array), strengths, weaknesses, recommendations, summary, confidence
"""

    gemini_payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.3,
            "responseMimeType": "application/json",
        },
    }
    failures: list[dict[str, Any]] = []

    for backend in backends:
        if backend == "openai":
            parsed, used_model, err = chat_json_object(
                prompt=prompt,
                api_key=openai_key,
                timeout=120.0,
            )
            if err is None and parsed is not None:
                report = _normalize_ai_payload(parsed)
                return {
                    "status": "ok",
                    "user_key": user_key,
                    "raw_summary": summary,
                    "ai_report": report.model_dump(),
                    "model": used_model,
                }
            failures.append({
                "provider": "openai",
                "error": err or "unknown",
                "model": used_model or "openai",
            })
            continue

        if not gemini_key:
            failures.append({
                "provider": "gemini",
                "error": "missing_api_key",
                "model": model,
            })
            continue

        if not gemini_key.isascii():
            failures.append({
                "provider": "gemini",
                "error": "non_ascii_api_key",
                "model": model,
            })
            continue

        try:
            models = parse_gemini_models()
            if not models:
                models = [model]
            response, used_model = post_generate_content_first_available(
                api_key=gemini_key,
                json_body=gemini_payload,
                models=models,
                timeout=60,
            )
            if response is None or response.status_code != 200:
                failures.append({
                    "provider": "gemini",
                    "error": f"http_{response.status_code if response else 'no_response'}",
                    "model": used_model or model,
                    "body_excerpt": (response.text or "")[:800] if response else "",
                })
                continue

            raw = response.json()
            report = _extract_ai_report(raw)
            return {
                "status": "ok",
                "user_key": user_key,
                "raw_summary": summary,
                "ai_report": report.model_dump(),
                "model": used_model,
            }
        except requests.RequestException as exc:
            failures.append({
                "provider": "gemini",
                "error": str(exc),
                "model": model,
            })
        except (json.JSONDecodeError, ValueError) as exc:
            failures.append({
                "provider": "gemini",
                "error": f"parse_error:{exc}",
                "model": model,
            })

    return {
        "status": "error",
        "message": "AI backends failed",
        "user_key": user_key,
        "providers_tried": backends,
        "failures": failures,
    }

def analyze_and_save_user_with_gemini(user_key: str) -> dict[str, Any]:
    result = analyze_user_with_gemini(user_key)

    if result.get("status") != "ok":
        return result

    write_ai_report(
        user_key=user_key,
        model_name=result["model"],
        raw_summary=result["raw_summary"],
        ai_report=result["ai_report"],
    )

    return {
        "status": "ok",
        "message": "AI report generated and saved",
        "user_key": user_key,
        "model": result["model"],
    }
