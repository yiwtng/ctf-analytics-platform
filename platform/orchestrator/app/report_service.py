import csv
import hashlib
import json
import os
import time
from typing import Any, Dict, List

import psycopg2
import psycopg2.extras

from app.gemini_http import parse_gemini_models, post_generate_content_first_available
from app.openai_client import available_ai_backends, chat_json_object


ANALYTICS_DB_HOST = os.getenv("ANALYTICS_DB_HOST", "analytics_db")
ANALYTICS_DB_PORT = int(os.getenv("ANALYTICS_DB_PORT", "5432"))
ANALYTICS_DB_NAME = os.getenv("ANALYTICS_DB_NAME", "analytics")
ANALYTICS_DB_USER = os.getenv("ANALYTICS_DB_USER", "analytics")
ANALYTICS_DB_PASSWORD = os.getenv("ANALYTICS_DB_PASSWORD", "analytics")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
GENERATE_REPORT_ALL_GAP_SECONDS = float(os.getenv("GENERATE_REPORT_ALL_GAP_SECONDS", "15"))
ROUND_COHORT_PATH = os.path.join(os.path.dirname(__file__), "data", "round_cohort.csv")
ROUND_COMPARISON_METRICS = [
    ("total_solves", "Solves"),
    ("accuracy_score", "Accuracy"),
    ("persistence_score", "Persistence"),
    ("protocol_score", "Protocol"),
    ("web_recon_score", "Web"),
    ("ssh_pivot_score", "SSH"),
    ("blue_analysis_score", "Blue"),
    ("time_efficiency_score", "Time"),
]

RED_CHALLENGES = {
    "red_ghost_login",
    "red_protocol_probe",
    "red_pivot_notes",
    "red_log_poisoning",
}

BLUE_CHALLENGES = {
    "blue_misleading_intel",
    "blue_slow_think_fast_guess",
    "blue_hint_dependency",
    "blue_multi_stage_flag",
    "blue_beacon_pattern",
    "blue_suspicious_archive",
    "blue_lateral_movement_clue",
    "blue_persistence_finder",
}


def get_db():
    return psycopg2.connect(
        host=ANALYTICS_DB_HOST,
        port=ANALYTICS_DB_PORT,
        dbname=ANALYTICS_DB_NAME,
        user=ANALYTICS_DB_USER,
        password=ANALYTICS_DB_PASSWORD,
    )


def clamp_score(v: int) -> int:
    return max(0, min(100, v))


def normalize_json_field(v: Any) -> Any:
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return v
    return v


def _normalize_ai_db_row(row: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not row:
        return None

    ai = dict(row)
    ai["profile"] = normalize_json_field(ai.get("profile"))
    ai["strengths"] = normalize_json_field(ai.get("strengths"))
    ai["weaknesses"] = normalize_json_field(ai.get("weaknesses"))
    ai["recommendations"] = normalize_json_field(ai.get("recommendations"))
    ai["raw_response"] = normalize_json_field(ai.get("raw_response"))
    return ai


def _ai_report_payload_from_row(ai_row: Dict[str, Any]) -> Dict[str, Any]:
    raw_response = ai_row.get("raw_response") or {}
    cached_report = raw_response.get("ai_report") if isinstance(raw_response, dict) else None
    if isinstance(cached_report, dict):
        return cached_report
    return {
        "profile": ai_row.get("profile", []),
        "strengths": ai_row.get("strengths", []),
        "weaknesses": ai_row.get("weaknesses", []),
        "recommendations": ai_row.get("recommendations", []),
        "summary": ai_row.get("summary", ""),
        "confidence": ai_row.get("confidence", "medium"),
    }


def _build_ai_input_signature(user_key: str, stats: Dict[str, Any], scores: Dict[str, Any]) -> str:
    payload = {
        "user_key": user_key,
        "stats": stats,
        "scores": scores,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _extract_cached_ai_signature(ai_row: Dict[str, Any] | None) -> str:
    if not ai_row:
        return ""
    raw_response = ai_row.get("raw_response") or {}
    if not isinstance(raw_response, dict):
        return ""
    cache_meta = raw_response.get("cache")
    if not isinstance(cache_meta, dict):
        return ""
    signature = cache_meta.get("input_signature")
    return str(signature or "").strip()


def _decorate_ai_result_for_cache(
    ai_result: Dict[str, Any],
    *,
    input_signature: str,
    user_key: str,
    stats: Dict[str, Any],
    scores: Dict[str, Any],
) -> Dict[str, Any]:
    raw_response = ai_result.get("raw_response")
    if not isinstance(raw_response, dict):
        raw_response = {"raw_response_text": str(raw_response or "")}
    else:
        raw_response = dict(raw_response)

    raw_response["cache"] = {
        "input_signature": input_signature,
        "user_key": user_key,
    }
    raw_response["ai_report"] = ai_result.get("ai_report", {})
    raw_response["raw_summary"] = {
        "stats": stats,
        "scores": scores,
    }

    out = dict(ai_result)
    out["raw_response"] = raw_response
    return out


def _get_latest_ai_row(user_key: str) -> Dict[str, Any] | None:
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM user_ai_reports
                WHERE user_key = %s
                ORDER BY generated_at DESC, id DESC
                LIMIT 1
                """,
                (user_key,),
            )
            row = cur.fetchone()
    return _normalize_ai_db_row(dict(row) if row else None)


def _get_cached_ai_result(user_key: str, input_signature: str) -> Dict[str, Any] | None:
    ai_row = _get_latest_ai_row(user_key)
    if not ai_row:
        return None
    if _extract_cached_ai_signature(ai_row) != input_signature:
        return None
    return {
        "id": ai_row.get("id"),
        "model": ai_row.get("model", "rule-based-fallback"),
        "ai_report": _ai_report_payload_from_row(ai_row),
        "raw_response": ai_row.get("raw_response") or {},
    }


def load_round_cohort() -> List[Dict[str, Any]]:
    if not os.path.exists(ROUND_COHORT_PATH):
        return []

    rows: List[Dict[str, Any]] = []
    with open(ROUND_COHORT_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "participant_id": row["participant_id"].strip(),
                "participant_name": row["participant_name"].strip(),
                "round_number": int(row["round_number"]),
                "username": row["username"].strip(),
                "email": row["email"].strip(),
                "password": row["password"].strip(),
                "notes": row.get("notes", "").strip(),
            })
    return rows


def get_round_participants() -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}

    for row in load_round_cohort():
        participant = grouped.setdefault(
            row["participant_id"],
            {
                "participant_id": row["participant_id"],
                "participant_name": row["participant_name"],
                "rounds": [],
            },
        )
        participant["rounds"].append(row)

    participants = list(grouped.values())
    participants.sort(key=lambda item: item["participant_id"])

    for participant in participants:
        participant["rounds"].sort(key=lambda item: item["round_number"])

    return participants


def get_latest_participant_feedback_for_user(user_key: str) -> Dict[str, Any] | None:
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    feedback_id,
                    ts,
                    user_key,
                    usability_score,
                    challenge_quality_score,
                    recommendation_quality_score,
                    confidence_improvement_score,
                    favorite_part,
                    improvement_point,
                    comments
                FROM participant_feedback
                WHERE user_key = %s
                ORDER BY ts DESC
                LIMIT 1
                """,
                (user_key,),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def _build_score_snapshot(skill_report: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not skill_report:
        return None

    return {
        "overall_level": skill_report.get("overall_level"),
        "total_solves": skill_report.get("total_solves", 0),
        "accuracy_score": skill_report.get("accuracy_score", 0),
        "persistence_score": skill_report.get("persistence_score", 0),
        "protocol_score": skill_report.get("protocol_score", 0),
        "web_recon_score": skill_report.get("web_recon_score", 0),
        "ssh_pivot_score": skill_report.get("ssh_pivot_score", 0),
        "blue_analysis_score": skill_report.get("blue_analysis_score", 0),
        "time_efficiency_score": skill_report.get("time_efficiency_score", 0),
    }


def _diff_string_lists(previous: List[str], current: List[str]) -> Dict[str, List[str]]:
    previous_set = set(previous or [])
    current_set = set(current or [])
    return {
        "added": sorted(current_set - previous_set),
        "removed": sorted(previous_set - current_set),
        "retained": sorted(current_set & previous_set),
    }


def _build_round_delta(previous_round: Dict[str, Any], current_round: Dict[str, Any]) -> Dict[str, Any] | None:
    previous_skill = previous_round.get("skill_report")
    current_skill = current_round.get("skill_report")
    previous_ai = previous_round.get("ai_report") or {}
    current_ai = current_round.get("ai_report") or {}

    if not previous_skill or not current_skill:
        return None

    metric_changes = []
    improved_metrics = []
    declined_metrics = []

    for key, label in ROUND_COMPARISON_METRICS:
        start = int(previous_skill.get(key) or 0)
        end = int(current_skill.get(key) or 0)
        delta = end - start
        direction = "same"
        if delta > 0:
            direction = "up"
            improved_metrics.append(label)
        elif delta < 0:
            direction = "down"
            declined_metrics.append(label)

        metric_changes.append({
            "key": key,
            "label": label,
            "start": start,
            "end": end,
            "delta": delta,
            "direction": direction,
        })

    recommendation_diff = _diff_string_lists(
        previous_ai.get("recommendations", []),
        current_ai.get("recommendations", []),
    )
    weakness_diff = _diff_string_lists(
        previous_ai.get("weaknesses", []),
        current_ai.get("weaknesses", []),
    )

    narrative_parts = []
    if improved_metrics:
        narrative_parts.append(f"พัฒนาขึ้นใน {', '.join(improved_metrics)}")
    if declined_metrics:
        narrative_parts.append(f"ลดลงใน {', '.join(declined_metrics)}")
    if weakness_diff["removed"]:
        narrative_parts.append(f"AI มองว่าจุดอ่อนบางส่วนลดลง เช่น {', '.join(weakness_diff['removed'][:2])}")
    if recommendation_diff["added"]:
        narrative_parts.append(f"AI เปลี่ยนคำแนะนำเพิ่มเติมเป็น {', '.join(recommendation_diff['added'][:2])}")

    return {
        "from_round": previous_round["round_number"],
        "to_round": current_round["round_number"],
        "metric_changes": metric_changes,
        "improved_metrics": improved_metrics,
        "declined_metrics": declined_metrics,
        "recommendation_diff": recommendation_diff,
        "weakness_diff": weakness_diff,
        "narrative": " | ".join(narrative_parts) if narrative_parts else "ยังไม่พบความเปลี่ยนแปลงเด่นชัด",
    }


def _build_participant_comparison(participant: Dict[str, Any]) -> Dict[str, Any]:
    rounds = []
    for round_info in participant["rounds"]:
        username = round_info["username"]
        report = get_latest_user_report(username)
        skill = report.get("skill_report")
        ai = report.get("ai_report")
        rounds.append({
            **round_info,
            "skill_report": skill,
            "ai_report": ai,
            "progress": report.get("progress", []),
            "percentile": report.get("percentile"),
            "participant_feedback": get_latest_participant_feedback_for_user(username),
            "score_snapshot": _build_score_snapshot(skill),
            # หน้าเปรียบเทียบต้องการทั้งรายงานทักษะและรายงาน AI
            "report_ready": bool(skill and ai),
        })

    completed_rounds = [round_item for round_item in rounds if round_item["report_ready"]]
    transitions = []
    for idx in range(1, len(rounds)):
        transition = _build_round_delta(rounds[idx - 1], rounds[idx])
        if transition:
            transitions.append(transition)

    baseline = completed_rounds[0] if completed_rounds else None
    latest = completed_rounds[-1] if completed_rounds else None
    # Compare by round_number, not dict equality (identical scores could make baseline == latest)
    same_round = (
        baseline
        and latest
        and baseline.get("round_number") == latest.get("round_number")
    )
    overall_change = (
        _build_round_delta(baseline, latest)
        if baseline and latest and not same_round
        else None
    )

    return {
        "participant_id": participant["participant_id"],
        "participant_name": participant["participant_name"],
        "rounds": rounds,
        "completed_rounds": len(completed_rounds),
        "comparison": {
            "overall_change": overall_change,
            "transitions": transitions,
        },
    }


def fetch_user_events(user_key: str) -> List[Dict[str, Any]]:
    sql = """
        SELECT
            ts,
            event_type,
            user_key,
            challenge_id,
            session_id,
            payload
        FROM events
        WHERE user_key = %s
        ORDER BY ts ASC
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (user_key,))
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def empty_stats() -> Dict[str, Any]:
    return {
        "total_opened": 0,
        "total_started": 0,
        "total_ready": 0,
        "total_solves": 0,
        "total_wrong_submits": 0,
        "total_giveups": 0,
        "total_errors": 0,
        "web_request": 0,
        "ssh_command": 0,
        "tcp_input": 0,
        "tcp_connect": 0,
        "tcp_auth_attempt": 0,
        "tcp_bad_auth": 0,
        "tcp_malformed": 0,
        "tcp_hello_ok": 0,
        "flag_found": 0,
        "web_solves": 0,
        "protocol_solves": 0,
        "ssh_solves": 0,
        "blue_opened": 0,
        "blue_unique_attempts": 0,
        "blue_solves": 0,
        "blue_wrong": 0,
        "blue_hint_use": 0,
        "ssh_errors": 0,
        "web_wrong_fast": 0,
        "excessive_restarts": 0,
        "by_challenge": {},
    }


def new_per_challenge_bucket() -> Dict[str, Any]:
    return {
        "opened": 0,
        "start_click": 0,
        "instance_ready": 0,
        "submit_wrong": 0,
        "submit_success": 0,
        "give_up": 0,
        "interaction_error": 0,
        "hint_use": 0,
        "web_request": 0,
        "ssh_command": 0,
        "tcp_auth_attempt": 0,
        "tcp_bad_auth": 0,
        "tcp_malformed": 0,
        "tcp_hello_ok": 0,
        "flag_found": 0,
        "solved": False,
    }


def mark_solved(stats: Dict[str, Any], pc: Dict[str, Any], challenge_id: str):
    if pc.get("solved"):
        return

    pc["solved"] = True
    pc["submit_success"] += 1
    stats["total_solves"] += 1

    if challenge_id in RED_CHALLENGES:
        if challenge_id in {"red_ghost_login", "red_log_poisoning"}:
            stats["web_solves"] += 1
        elif challenge_id == "red_protocol_probe":
            stats["protocol_solves"] += 1
        elif challenge_id == "red_pivot_notes":
            stats["ssh_solves"] += 1
    elif challenge_id in BLUE_CHALLENGES:
        stats["blue_solves"] += 1


def detect_behavior_profiles(stats: Dict[str, Any]) -> List[str]:
    profile = []

    if stats["tcp_bad_auth"] >= 5:
        profile.append("มีแนวโน้มใช้การลองยืนยันตัวตนหลายครั้งกับบริการเครือข่าย")

    if stats["total_wrong_submits"] == 0 and stats["total_solves"] > 0:
        profile.append("มีความแม่นยำสูงในการส่งคำตอบ")

    if stats["total_giveups"] > 0:
        profile.append("มีแนวโน้มยอมแพ้ในบางโจทย์เมื่อไม่สามารถดำเนินต่อได้")

    if stats["protocol_solves"] > 0 and stats["tcp_hello_ok"] > 0:
        profile.append("มีความสามารถด้าน protocol interaction และการวิเคราะห์บริการเครือข่าย")

    if stats["ssh_solves"] == 0:
        profile.append("ยังควรพัฒนาทักษะด้าน SSH pivoting และ multi-step exploitation")

    if stats["web_solves"] == 0 and stats["web_request"] == 0:
        profile.append("มีการใช้งานโจทย์กลุ่ม Web ค่อนข้างน้อยเมื่อเทียบกับโจทย์เชิงโปรโตคอล")

    if stats.get("blue_unique_attempts", 0) >= 2 and stats.get("blue_solves", 0) > 0:
        profile.append("มีแนวโน้มเชื่อมโยงหลักฐานในโจทย์ Blue Team ได้ดีขึ้นจากการทดลองหลายโจทย์")
    elif stats.get("blue_opened", 0) > 0 and stats.get("blue_solves", 0) == 0:
        profile.append("มีความพยายามสำรวจโจทย์ Blue Team แต่ยังควรพัฒนาการสรุปหลักฐานไปสู่คำตอบสุดท้าย")

    return profile


def aggregate_user_stats(user_key: str) -> Dict[str, Any]:
    events = fetch_user_events(user_key)
    stats = empty_stats()
    per_challenge: Dict[str, Dict[str, Any]] = {}

    for row in events:
        event_type = row.get("event_type")
        challenge_id = row.get("challenge_id")
        payload = row.get("payload") or {}

        if challenge_id and challenge_id not in per_challenge:
            per_challenge[challenge_id] = new_per_challenge_bucket()

        pc = per_challenge.get(challenge_id)

        if event_type == "CHALLENGE_OPEN_UI":
            stats["total_opened"] += 1
            if challenge_id in BLUE_CHALLENGES:
                stats["blue_opened"] += 1
            if pc:
                pc["opened"] += 1

        elif event_type == "START_INSTANCE_UI_CLICK":
            stats["total_started"] += 1
            if pc:
                pc["start_click"] += 1

        elif event_type == "INSTANCE_READY_UI":
            stats["total_ready"] += 1
            if pc:
                pc["instance_ready"] += 1

        elif event_type == "FLAG_SUBMIT_RESULT":
            result = str(payload.get("result", "")).lower()
            response_excerpt = str(payload.get("response_excerpt", "")).lower()

            is_wrong = result == "wrong" or "incorrect" in response_excerpt or "wrong" in response_excerpt
            is_success = result == "submitted" or "correct" in response_excerpt or "solves" in response_excerpt

            if challenge_id in RED_CHALLENGES:
                if is_wrong:
                    stats["total_wrong_submits"] += 1
                    if pc:
                        pc["submit_wrong"] += 1
                elif is_success and pc:
                    mark_solved(stats, pc, challenge_id)

            elif challenge_id in BLUE_CHALLENGES:
                if is_wrong:
                    stats["total_wrong_submits"] += 1
                    stats["blue_wrong"] += 1
                    if pc:
                        pc["submit_wrong"] += 1
                elif is_success and pc:
                    mark_solved(stats, pc, challenge_id)

        elif event_type == "FLAG_FOUND":
            stats["flag_found"] += 1
            if pc:
                pc["flag_found"] += 1
                if challenge_id in RED_CHALLENGES or challenge_id in BLUE_CHALLENGES:
                    mark_solved(stats, pc, challenge_id)

        elif event_type == "CHALLENGE_GIVE_UP":
            stats["total_giveups"] += 1
            if pc:
                pc["give_up"] += 1

        elif event_type in {"CHALLENGE_INTERACTION_ERROR", "FLAG_SUBMIT_ERROR", "START_INSTANCE_FAILED", "SIM_USER_ERROR"}:
            stats["total_errors"] += 1
            if pc:
                pc["interaction_error"] += 1
            if challenge_id == "red_pivot_notes":
                stats["ssh_errors"] += 1

        elif event_type == "WEB_REQUEST":
            stats["web_request"] += 1
            if pc:
                pc["web_request"] += 1

        elif event_type == "SSH_COMMAND":
            stats["ssh_command"] += 1
            if pc:
                pc["ssh_command"] += 1

        elif event_type == "TCP_INPUT":
            stats["tcp_input"] += 1

        elif event_type == "TCP_CONNECT":
            stats["tcp_connect"] += 1

        elif event_type == "TCP_AUTH_ATTEMPT":
            stats["tcp_auth_attempt"] += 1
            if pc:
                pc["tcp_auth_attempt"] += 1

        elif event_type == "TCP_BAD_AUTH":
            stats["tcp_bad_auth"] += 1
            if pc:
                pc["tcp_bad_auth"] += 1

        elif event_type == "TCP_MALFORMED":
            stats["tcp_malformed"] += 1
            if pc:
                pc["tcp_malformed"] += 1

        elif event_type == "TCP_HELLO_OK":
            stats["tcp_hello_ok"] += 1
            if pc:
                pc["tcp_hello_ok"] += 1

        elif event_type == "HINT_UNLOCK_UI":
            if challenge_id in BLUE_CHALLENGES:
                stats["blue_hint_use"] += 1
            if pc:
                pc["hint_use"] += 1

    for challenge_id, pc in per_challenge.items():
        if pc["start_click"] >= 3 and not pc["solved"]:
            stats["excessive_restarts"] += 1

        if challenge_id in {"red_ghost_login", "red_log_poisoning"} and pc["submit_wrong"] >= 1 and pc["web_request"] <= 2:
            stats["web_wrong_fast"] += 1

        if challenge_id in BLUE_CHALLENGES and (
            pc["opened"] > 0
            or pc["submit_wrong"] > 0
            or pc["submit_success"] > 0
            or pc["hint_use"] > 0
        ):
            stats["blue_unique_attempts"] += 1

    stats["by_challenge"] = per_challenge
    return stats


def derive_scores(stats: Dict[str, Any]) -> Dict[str, Any]:
    total_submit = stats["total_solves"] + stats["total_wrong_submits"]
    accuracy = 100 if total_submit == 0 else int((stats["total_solves"] / total_submit) * 100)

    persistence = clamp_score(
        40
        + stats["total_started"] * 5
        - stats["total_giveups"] * 10
        - stats["total_errors"] * 3
    )

    web_recon = clamp_score(
        50
        + stats.get("web_request", 0) * 2
        - stats.get("web_wrong_fast", 0) * 8
        + stats.get("web_solves", 0) * 15
    )

    protocol = clamp_score(
        50
        + stats.get("tcp_hello_ok", 0) * 10
        + stats.get("protocol_solves", 0) * 20
        - stats.get("tcp_malformed", 0) * 6
        - stats.get("tcp_bad_auth", 0) * 5
    )

    ssh_pivot = clamp_score(
        50
        + stats.get("ssh_command", 0) * 3
        + stats.get("ssh_solves", 0) * 20
        - stats.get("ssh_errors", 0) * 8
    )

    blue_analysis = clamp_score(
        50
        + stats.get("blue_unique_attempts", 0) * 4
        + min(stats.get("blue_opened", 0), 10)
        + stats.get("blue_solves", 0) * 12
        - stats.get("blue_wrong", 0) * 4
        - stats.get("blue_hint_use", 0) * 3
    )

    time_eff = clamp_score(
        70
        - stats.get("excessive_restarts", 0) * 10
        - stats["total_wrong_submits"] * 3
        - stats["total_errors"] * 3
    )

    overall_avg = int((web_recon + protocol + ssh_pivot + blue_analysis + persistence + accuracy + time_eff) / 7)

    if overall_avg >= 80:
        level = "Advanced"
    elif overall_avg >= 60:
        level = "Intermediate"
    else:
        level = "Developing"

    return {
        "web_recon_score": web_recon,
        "protocol_score": protocol,
        "ssh_pivot_score": ssh_pivot,
        "blue_analysis_score": blue_analysis,
        "persistence_score": persistence,
        "accuracy_score": accuracy,
        "time_efficiency_score": time_eff,
        "overall_level": level,
        "overall_average": overall_avg,
    }


def build_gemini_prompt(user_key: str, stats: Dict[str, Any], scores: Dict[str, Any]) -> str:
    profiles = detect_behavior_profiles(stats)

    return f"""
คุณคือผู้เชี่ยวชาญด้าน Cybersecurity Training และทำหน้าที่เป็นโค้ชให้ผู้เรียน

ให้วิเคราะห์พฤติกรรมของผู้เล่นจากข้อมูลด้านล่าง และสร้างรายงานภาษาไทยเท่านั้น

ชื่อผู้เล่น: {user_key}

ข้อมูลพฤติกรรม:
{json.dumps(stats, ensure_ascii=False, indent=2)}

คะแนนที่คำนวณได้:
{json.dumps(scores, ensure_ascii=False, indent=2)}

พฤติกรรมเบื้องต้นที่ตรวจพบ:
{json.dumps(profiles, ensure_ascii=False, indent=2)}

ให้ตอบกลับเป็น JSON เท่านั้น ตามโครงสร้างนี้:

{{
  "profile": ["..."],
  "strengths": ["..."],
  "weaknesses": ["..."],
  "recommendations": ["..."],
  "evidence": ["..."],
  "summary": "...",
  "confidence": "low|medium|high"
}}

ข้อกำหนด:
- เขียนเป็นภาษาไทยทั้งหมด
- ใช้ภาษาที่เข้าใจง่าย แต่เป็นทางการระดับงานวิจัย
- recommendations ต้องนำไปฝึกต่อได้จริง
- เพิ่ม evidence ที่อธิบายเหตุผลเชิงข้อมูลจริง เช่น จำนวน event ที่สำคัญ
- วิเคราะห์ทั้งมุม Red Team และ Blue Team ถ้ามี
- ห้ามตอบนอก JSON
""".strip()


def build_rule_based_ai_report(user_key: str, stats: Dict[str, Any], scores: Dict[str, Any]) -> Dict[str, Any]:
    def _unique(items: List[str]) -> List[str]:
        seen = set()
        out: List[str] = []
        for item in items:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            out.append(text)
        return out

    total_solves = int(stats.get("total_solves", 0) or 0)
    accuracy = int(scores.get("accuracy_score", 0) or 0)
    level = str(scores.get("overall_level", "Developing") or "Developing")

    profiles: List[str] = []
    if total_solves >= 3 and accuracy >= 80:
        profiles.append("มีแนวโน้มวางแผนการแก้โจทย์ได้เป็นระบบ และตัดสินใจได้แม่นยำขึ้นอย่างชัดเจน")
    elif total_solves >= 1:
        profiles.append("เริ่มเปลี่ยนจากการสำรวจแบบกว้างไปสู่การแก้โจทย์ได้อย่างมีทิศทางมากขึ้น")
    else:
        profiles.append("มีความพยายามในการทดลองหลายแนวทาง แต่ยังต้องพัฒนาการเชื่อมโยงข้อมูลที่พบไปสู่การแก้โจทย์ให้ชัดเจนขึ้น")

    profiles.extend(detect_behavior_profiles(stats))
    profiles = _unique(profiles) or ["วิเคราะห์จากรูปแบบการใช้งานและผลลัพธ์ที่ระบบบันทึกได้"]

    strengths: List[str] = []
    weaknesses: List[str] = []
    recommendations: List[str] = []
    evidence: List[str] = []

    if scores.get("accuracy_score", 0) >= 80:
        strengths.append("มีความแม่นยำสูงในการตัดสินใจส่งคำตอบ")
    elif stats.get("total_wrong_submits", 0) >= 3:
        weaknesses.append("ยังมีแนวโน้มส่งคำตอบผิดหลายครั้งก่อนจะพบแนวทางที่ถูกต้อง")
        recommendations.append("ทบทวนหลักฐานก่อนส่งคำตอบทุกครั้ง และสรุปสมมติฐานให้ชัดเจนก่อนตัดสินใจ submit")

    if scores.get("protocol_score", 0) >= 75:
        strengths.append("มีความเข้าใจลำดับการโต้ตอบของบริการเครือข่ายค่อนข้างดี")
    elif stats.get("tcp_input", 0) > 0:
        weaknesses.append("ยังควรพัฒนาความเข้าใจเชิงลำดับขั้นของ protocol และกระบวนการยืนยันตัวตน")
        recommendations.append("ฝึกอ่าน flow ของบริการทีละขั้น ลดการลองแบบสุ่ม และสังเกตข้อความตอบกลับของบริการให้เป็นระบบ")

    if scores.get("web_recon_score", 0) >= 75:
        strengths.append("มีการสำรวจโจทย์เชิงเว็บอย่างต่อเนื่องและค่อนข้างครอบคลุม")
    elif stats.get("web_request", 0) > 0:
        weaknesses.append("การสำรวจเว็บยังไม่เชื่อมโยงไปสู่การแก้โจทย์ได้อย่างมีประสิทธิภาพ")
        recommendations.append("จัดลำดับการสำรวจเว็บให้ชัดเจน เช่น เก็บ endpoint สำคัญ พารามิเตอร์ และเงื่อนไขที่พบก่อนทดลองโจมตี")

    if scores.get("ssh_pivot_score", 0) >= 75:
        strengths.append("แสดงศักยภาพที่ดีด้าน SSH pivoting และการทำโจทย์แบบหลายขั้นตอน")
    elif stats.get("ssh_command", 0) > 0 or stats.get("ssh_solves", 0) == 0:
        weaknesses.append("ทักษะด้าน SSH pivoting และ post-exploitation ยังไม่สม่ำเสมอ")
        recommendations.append("ฝึกสำรวจ host ผ่าน SSH แบบเป็นขั้นตอน เริ่มจาก enumeration ก่อนขยับไปยังการค้นหาเส้นทางสู่ flag")

    if scores.get("blue_analysis_score", 0) >= 75:
        strengths.append("สามารถเชื่อมโยงหลักฐานในโจทย์ Blue Team ได้ค่อนข้างเป็นระบบ")
    elif stats.get("blue_opened", 0) > 0:
        weaknesses.append("การวิเคราะห์โจทย์ Blue Team ยังเปลี่ยนเป็นคำตอบที่แม่นยำได้ไม่สม่ำเสมอ")
        recommendations.append("ฝึกสรุปเหตุผลจาก log, timeline และ artifact เป็นข้อสรุปสั้น ๆ ก่อนตัดสินใจส่งคำตอบ")

    if scores.get("persistence_score", 0) >= 70:
        strengths.append("มีความพยายามต่อเนื่องในการเริ่มต้นและดำเนินโจทย์จนจบรอบ")
    elif stats.get("total_giveups", 0) > 0:
        weaknesses.append("มีแนวโน้มยุติการแก้โจทย์ก่อนทดลองทางเลือกให้ครบถ้วน")
        recommendations.append("กำหนด checklist ของแนวทางที่ต้องลองก่อนตัดสินใจยุติโจทย์ เพื่อไม่ให้พลาดวิธีที่ยังไม่ได้ตรวจสอบ")

    if stats.get("tcp_bad_auth", 0) > 0:
        evidence.append(f"TCP_BAD_AUTH: {stats['tcp_bad_auth']}")
    if stats.get("tcp_hello_ok", 0) > 0:
        evidence.append(f"TCP_HELLO_OK: {stats['tcp_hello_ok']}")
    if stats.get("web_request", 0) > 0:
        evidence.append(f"WEB_REQUEST: {stats['web_request']}")
    if stats.get("ssh_command", 0) > 0:
        evidence.append(f"SSH_COMMAND: {stats['ssh_command']}")
    if stats.get("blue_opened", 0) > 0:
        evidence.append(f"BLUE_CHALLENGE_OPEN_UI: {stats['blue_opened']}")
    if stats.get("blue_unique_attempts", 0) > 0:
        evidence.append(f"blue_unique_attempts: {stats['blue_unique_attempts']}")
    if stats.get("blue_solves", 0) > 0:
        evidence.append(f"blue_solves: {stats['blue_solves']}")
    if stats.get("blue_wrong", 0) > 0:
        evidence.append(f"blue_wrong: {stats['blue_wrong']}")
    if stats.get("blue_hint_use", 0) > 0:
        evidence.append(f"blue_hint_use: {stats['blue_hint_use']}")
    if stats.get("total_wrong_submits", 0) > 0:
        evidence.append(f"FLAG_SUBMIT_RESULT ผิด: {stats['total_wrong_submits']}")
    evidence.extend([
        f"total_solves: {stats.get('total_solves', 0)}",
        f"accuracy_score: {scores.get('accuracy_score', 0)}",
        f"protocol_score: {scores.get('protocol_score', 0)}",
        f"web_recon_score: {scores.get('web_recon_score', 0)}",
        f"ssh_pivot_score: {scores.get('ssh_pivot_score', 0)}",
        f"time_efficiency_score: {scores.get('time_efficiency_score', 0)}",
    ])

    strengths = _unique(strengths)
    weaknesses = _unique(weaknesses)
    recommendations = _unique(recommendations)
    evidence = _unique(evidence)

    if not strengths:
        strengths.append("มีข้อมูลพฤติกรรมเพียงพอสำหรับใช้เป็นฐานในการสะท้อนผลและวางแผนพัฒนารอบถัดไป")
    if not weaknesses:
        weaknesses.append("ยังไม่พบจุดอ่อนเด่นชัดจากข้อมูลรอบนี้ แต่ควรติดตามพฤติกรรมอย่างต่อเนื่องในรอบถัดไป")
    if not recommendations:
        recommendations.append("รักษาแนวทางการแก้โจทย์แบบเป็นขั้นตอน และบันทึกสิ่งที่ลองแล้วทุกครั้งเพื่อใช้ทบทวนหลังจบรอบ")

    if total_solves >= 3:
        progress_note = "สะท้อนว่ามีความพร้อมในการจัดการโจทย์หลายรูปแบบได้ค่อนข้างดี"
    elif total_solves >= 1:
        progress_note = "สะท้อนว่าเริ่มเปลี่ยนจากการสำรวจไปสู่การแก้โจทย์ได้จริงมากขึ้น"
    else:
        progress_note = "สะท้อนว่ายังอยู่ในช่วงสะสมประสบการณ์และปรับวิธีคิดในการแก้โจทย์"

    summary = (
        f"จากข้อมูลรอบนี้ ผู้เล่น {user_key} อยู่ในระดับ {level} "
        f"และสามารถแก้โจทย์ได้ {total_solves} โจทย์ ด้วยความแม่นยำ {accuracy} คะแนน "
        f"{progress_note} จุดเด่นหลักคือ {strengths[0]} "
        f"ขณะที่ประเด็นที่ควรพัฒนาต่อคือ {weaknesses[0]}"
    )

    return {
        "profile": profiles[:3],
        "strengths": strengths[:5],
        "weaknesses": weaknesses[:5],
        "recommendations": recommendations[:5],
        "evidence": evidence[:10],
        "summary": summary,
        "confidence": "medium",
    }


def _analyze_user_with_openai(user_key: str, stats: Dict[str, Any], scores: Dict[str, Any]) -> tuple[bool, Dict[str, Any]]:
    prompt = build_gemini_prompt(user_key, stats, scores)
    parsed, used_model, err = chat_json_object(
        prompt=prompt,
        api_key=OPENAI_API_KEY,
        timeout=120.0,
    )
    if err is None and isinstance(parsed, dict):
        return True, {
            "model": used_model,
            "ai_report": parsed,
            "raw_response": {"provider": "openai"},
        }

    return False, {
        "provider": "openai",
        "error": err or "unknown",
        "model": used_model or "openai",
    }


def _analyze_user_with_gemini_provider(
    user_key: str,
    stats: Dict[str, Any],
    scores: Dict[str, Any],
) -> tuple[bool, Dict[str, Any]]:
    if not GEMINI_API_KEY:
        return False, {
            "provider": "gemini",
            "error": "missing_api_key",
            "model": GEMINI_MODEL,
        }

    prompt = build_gemini_prompt(user_key, stats, scores)

    payload = {
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

    models = parse_gemini_models()
    if not models:
        models = [GEMINI_MODEL]

    resp, used_model = post_generate_content_first_available(
        api_key=GEMINI_API_KEY,
        json_body=payload,
        models=models,
        timeout=60,
    )
    if resp is None or resp.status_code != 200:
        if resp is not None:
            return False, {
                "provider": "gemini",
                "error": "rate_limited" if resp.status_code == 429 else (
                    "service_unavailable" if resp.status_code == 503 else f"http_{resp.status_code}"
                ),
                "status_code": resp.status_code,
                "body_excerpt": (resp.text or "")[:2000],
                "model": used_model or GEMINI_MODEL,
            }
        return False, {
            "provider": "gemini",
            "error": "no_response",
            "model": used_model or GEMINI_MODEL,
        }
    raw = resp.json()

    text = ""
    candidates = raw.get("candidates", [])
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        if parts:
            text = parts[0].get("text", "")

    try:
        parsed = json.loads(text)
    except Exception:
        parsed = {
            "profile": ["ไม่สามารถแปลงผลลัพธ์ AI ได้สมบูรณ์"],
            "strengths": [],
            "weaknesses": [],
            "recommendations": ["ตรวจสอบ raw response ของ Gemini เพิ่มเติม"],
            "evidence": [],
            "summary": text[:1000],
            "confidence": "low",
        }

    return True, {
        "model": used_model or GEMINI_MODEL,
        "ai_report": parsed,
        "raw_response": {
            "provider": "gemini",
            "gemini_raw": raw,
        },
    }


def analyze_user_with_gemini(user_key: str, stats: Dict[str, Any], scores: Dict[str, Any]) -> Dict[str, Any]:
    backends = available_ai_backends()
    if not backends:
        return {
            "model": "rule-based-fallback",
            "ai_report": build_rule_based_ai_report(user_key, stats, scores),
            "raw_response": {"providers_tried": []},
        }

    failures: List[Dict[str, Any]] = []
    for backend in backends:
        if backend == "openai":
            ok, result = _analyze_user_with_openai(user_key, stats, scores)
        else:
            ok, result = _analyze_user_with_gemini_provider(user_key, stats, scores)

        if ok:
            raw_response = result.get("raw_response")
            if isinstance(raw_response, dict):
                raw_response["providers_tried"] = backends
            return result

        failures.append(result)

    return {
        "model": "rule-based-fallback",
        "ai_report": build_rule_based_ai_report(user_key, stats, scores),
        "raw_response": {
            "providers_tried": backends,
            "provider_failures": failures,
        },
    }


def save_skill_report(user_key: str, stats: Dict[str, Any], scores: Dict[str, Any]) -> int:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_skill_reports (
                    user_key,
                    total_opened,
                    total_started,
                    total_ready,
                    total_solves,
                    total_wrong_submits,
                    total_giveups,
                    total_errors,
                    web_recon_score,
                    protocol_score,
                    ssh_pivot_score,
                    blue_analysis_score,
                    persistence_score,
                    accuracy_score,
                    time_efficiency_score,
                    overall_level,
                    summary_json
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (
                    user_key,
                    stats["total_opened"],
                    stats["total_started"],
                    stats["total_ready"],
                    stats["total_solves"],
                    stats["total_wrong_submits"],
                    stats["total_giveups"],
                    stats["total_errors"],
                    scores["web_recon_score"],
                    scores["protocol_score"],
                    scores["ssh_pivot_score"],
                    scores["blue_analysis_score"],
                    scores["persistence_score"],
                    scores["accuracy_score"],
                    scores["time_efficiency_score"],
                    scores["overall_level"],
                    json.dumps(
                        {
                            "stats": stats,
                            "scores": scores,
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            inserted_id = cur.fetchone()[0]
        conn.commit()
    return inserted_id


def save_ai_report(user_key: str, ai_result: Dict[str, Any]) -> int:
    ai_report = ai_result["ai_report"]

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_ai_reports (
                    user_key,
                    model,
                    profile,
                    strengths,
                    weaknesses,
                    recommendations,
                    summary,
                    confidence,
                    raw_response
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (
                    user_key,
                    ai_result.get("model", "gemini"),
                    json.dumps(ai_report.get("profile", []), ensure_ascii=False),
                    json.dumps(ai_report.get("strengths", []), ensure_ascii=False),
                    json.dumps(ai_report.get("weaknesses", []), ensure_ascii=False),
                    json.dumps(ai_report.get("recommendations", []), ensure_ascii=False),
                    ai_report.get("summary", ""),
                    ai_report.get("confidence", "medium"),
                    json.dumps(ai_result.get("raw_response", {}), ensure_ascii=False),
                ),
            )
            inserted_id = cur.fetchone()[0]
        conn.commit()
    return inserted_id


def get_user_progress(user_key: str) -> List[Dict[str, Any]]:
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    generated_at,
                    total_solves,
                    accuracy_score,
                    persistence_score,
                    protocol_score,
                    web_recon_score,
                    ssh_pivot_score,
                    blue_analysis_score,
                    time_efficiency_score,
                    overall_level
                FROM user_skill_reports
                WHERE user_key = %s
                ORDER BY generated_at ASC
                """,
                (user_key,),
            )
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def get_user_percentile(user_key: str) -> int | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_key, AVG(accuracy_score)::float AS avg_accuracy
                FROM user_skill_reports
                GROUP BY user_key
                ORDER BY avg_accuracy
                """
            )
            rows = cur.fetchall()

    if not rows:
        return None

    found = None
    scores = []

    for row in rows:
        scores.append(row[1])
        if row[0] == user_key:
            found = row[1]

    if found is None:
        return None

    try:
        rank_index = scores.index(found)
    except ValueError:
        return None

    percentile = int((rank_index / max(1, len(scores))) * 100)
    return percentile


def generate_user_report(user_key: str, user_id: int | None = None) -> Dict[str, Any]:
    """
    Generate skill report and (conditionally) AI report for a user.

    AI report is only generated when the user is assigned to the TREATMENT
    condition. Control-group users receive skill scores only.
    Pass `user_id` (CTFd integer ID) to enable experiment gating;
    omit to always generate AI report (legacy / admin use).
    """
    from app.experiment import is_treatment  # local import to avoid circular deps

    stats = aggregate_user_stats(user_key)
    scores = derive_scores(stats)
    input_signature = _build_ai_input_signature(user_key, stats, scores)

    skill_report_id = save_skill_report(user_key, stats, scores)

    # Experiment gate: skip AI for control-group users
    generate_ai = (user_id is None) or is_treatment(user_id)

    if not generate_ai:
        return {
            "status": "ok",
            "user_key": user_key,
            "skill_report_id": skill_report_id,
            "ai_report_id": None,
            "scores": scores,
            "ai_report": None,
            "ai_cached": False,
            "condition": "control",
        }

    cached_ai = _get_cached_ai_result(user_key, input_signature)

    if cached_ai:
        ai_result = {
            "model": cached_ai.get("model", "rule-based-fallback"),
            "ai_report": cached_ai.get("ai_report", {}),
            "raw_response": cached_ai.get("raw_response", {}),
        }
        ai_report_id = cached_ai.get("id")
        ai_cached = True
    else:
        ai_result = analyze_user_with_gemini(user_key, stats, scores)
        ai_result = _decorate_ai_result_for_cache(
            ai_result,
            input_signature=input_signature,
            user_key=user_key,
            stats=stats,
            scores=scores,
        )
        ai_report_id = save_ai_report(user_key, ai_result)
        ai_cached = False

    return {
        "status": "ok",
        "user_key": user_key,
        "skill_report_id": skill_report_id,
        "ai_report_id": ai_report_id,
        "scores": scores,
        "ai_report": ai_result["ai_report"],
        "ai_cached": ai_cached,
        "condition": "treatment",
    }


def get_latest_user_report(user_key: str) -> Dict[str, Any]:
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM user_skill_reports
                WHERE user_key = %s
                ORDER BY generated_at DESC
                LIMIT 1
                """,
                (user_key,),
            )
            skill = cur.fetchone()

            cur.execute(
                """
                SELECT *
                FROM user_ai_reports
                WHERE user_key = %s
                ORDER BY generated_at DESC, id DESC
                LIMIT 1
                """,
                (user_key,),
            )
            ai = cur.fetchone()

    if skill:
        skill = dict(skill)
        skill["summary_json"] = normalize_json_field(skill.get("summary_json"))

    ai = _normalize_ai_db_row(dict(ai) if ai else None)

    return {
        "status": "ok",
        "user_key": user_key,
        "skill_report": skill,
        "ai_report": ai,
        "progress": get_user_progress(user_key),
        "percentile": get_user_percentile(user_key),
    }


def get_all_users_with_events() -> List[str]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT user_key
                FROM events
                WHERE user_key IS NOT NULL
                  AND user_key <> ''
                ORDER BY user_key
            """)
            rows = cur.fetchall()
    return [r[0] for r in rows]


def get_round_comparison_participant(participant_id: str) -> Dict[str, Any]:
    participants = get_round_participants()
    participant = next((item for item in participants if item["participant_id"] == participant_id), None)

    if not participant:
        return {
            "status": "error",
            "message": f"participant not found: {participant_id}",
        }

    return {
        "status": "ok",
        "participant": _build_participant_comparison(participant),
    }


def get_round_comparison_all() -> Dict[str, Any]:
    participants = [_build_participant_comparison(item) for item in get_round_participants()]
    complete_participants = [item for item in participants if item["completed_rounds"] == len(item["rounds"])]

    accuracy_deltas = []
    solve_deltas = []
    for participant in participants:
        overall = participant["comparison"].get("overall_change")
        if not overall:
            continue
        for metric in overall["metric_changes"]:
            if metric["key"] == "accuracy_score":
                accuracy_deltas.append(metric["delta"])
            elif metric["key"] == "total_solves":
                solve_deltas.append(metric["delta"])

    return {
        "status": "ok",
        "count": len(participants),
        "participants": participants,
        "summary": {
            "participants_total": len(participants),
            "participants_with_all_rounds": len(complete_participants),
            "avg_accuracy_delta": round(sum(accuracy_deltas) / len(accuracy_deltas), 2) if accuracy_deltas else 0,
            "avg_solves_delta": round(sum(solve_deltas) / len(solve_deltas), 2) if solve_deltas else 0,
        },
    }


def generate_all_reports() -> Dict[str, Any]:
    users = get_all_users_with_events()
    results = []

    for index, user_key in enumerate(users):
        try:
            result = generate_user_report(user_key)
            results.append(result)
        except Exception as exc:
            results.append({
                "status": "error",
                "user_key": user_key,
                "error": str(exc),
            })
            result = None
        if (
            index < len(users) - 1
            and GENERATE_REPORT_ALL_GAP_SECONDS > 0
            and result
            and not result.get("ai_cached")
        ):
            time.sleep(GENERATE_REPORT_ALL_GAP_SECONDS)

    return {
        "status": "ok",
        "count": len(results),
        "results": results,
    }