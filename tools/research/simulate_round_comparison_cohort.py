#!/usr/bin/env python3
"""
Simulate a 3-participant x 3-round study cohort for the round comparison page.

The script creates distinct behavior trajectories per participant while keeping
the overall direction consistent: each participant improves across rounds after
receiving earlier feedback.

Usage:
    python3 ctfd_tools/simulate_round_comparison_cohort.py
    python3 ctfd_tools/simulate_round_comparison_cohort.py --participant bank_s
    python3 ctfd_tools/simulate_round_comparison_cohort.py --participant bank_s --max-round 2
    python3 ctfd_tools/simulate_round_comparison_cohort.py --participant mint_s --min-round 3 --max-round 3

Environment:
    ORCH_BASE=http://orch.100.113.75.64.nip.io
    COHORT_CSV=/home/parallels/ctf-prod/orchestrator/app/data/round_cohort.csv
    REQUEST_TIMEOUT=20
    PAUSE_SCALE=1.0
    REPORT_GAP_SECONDS=15
"""

from __future__ import annotations

import argparse
import csv
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import os
import requests

ORCH_BASE = os.getenv("ORCH_BASE", "http://orch.100.113.75.64.nip.io").rstrip("/")
COHORT_CSV = Path(
    os.getenv(
        "COHORT_CSV",
        "/home/parallels/ctf-prod/orchestrator/app/data/round_cohort.csv",
    )
)
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))
PAUSE_SCALE = float(os.getenv("PAUSE_SCALE", "1.0"))
REPORT_GAP_SECONDS = float(os.getenv("REPORT_GAP_SECONDS", "15"))

RANDOM_SEED = 20260407

CHALLENGE_WEB = "red_ghost_login"
CHALLENGE_NC = "red_protocol_probe"
CHALLENGE_SSH = "red_pivot_notes"


@dataclass
class RoundUser:
    participant_id: str
    participant_name: str
    round_number: int
    username: str
    notes: str


STUDY_PROFILES: Dict[str, Dict[int, Dict[str, Any]]] = {
    "bank_s": {
        1: {
            "theme": "impulsive_baseline",
            "web": {"requests": 4, "probes": 3, "login_fail": 6, "wrong_submit": 2, "success_submit": 0},
            "nc": {"inputs": 5, "hello_ok": 0, "auth_attempt": 1, "bad_auth": 4, "malformed": 2, "flag_found": 0},
            "ssh": {"commands": ["pwd", "ls", "whoami"], "flag_attempt": 0, "flag_found": 0},
            "survey": {
                "usability_score": 3,
                "challenge_quality_score": 4,
                "recommendation_quality_score": 2,
                "confidence_improvement_score": 2,
                "favorite_part": "รู้สึกว่ามีหลายวิธีให้ลอง",
                "improvement_point": "ยังเดาเยอะเกินไปและไม่ค่อยวางแผนก่อนทำ",
                "comments": "รอบแรกยังใช้ brute-force และ trial-and-error เยอะ",
            },
        },
        2: {
            "theme": "less_guessing",
            "web": {"requests": 6, "probes": 2, "login_fail": 3, "wrong_submit": 1, "success_submit": 1},
            "nc": {"inputs": 4, "hello_ok": 1, "auth_attempt": 2, "bad_auth": 2, "malformed": 1, "flag_found": 1},
            "ssh": {"commands": ["pwd", "ls -la", "find /home -maxdepth 2 -type f 2>/dev/null"], "flag_attempt": 1, "flag_found": 0},
            "survey": {
                "usability_score": 4,
                "challenge_quality_score": 4,
                "recommendation_quality_score": 4,
                "confidence_improvement_score": 3,
                "favorite_part": "เริ่มจับ pattern ของ protocol ได้ดีขึ้น",
                "improvement_point": "ยังต้องลด bad auth และหาทางเข้าฝั่ง SSH ให้เป็นระบบขึ้น",
                "comments": "หลังอ่านคำแนะนำรอบแรก เลยเปลี่ยนไปอ่าน flow ก่อนยิงหลายครั้ง",
            },
        },
        3: {
            "theme": "methodical_improvement",
            "web": {"requests": 7, "probes": 1, "login_fail": 1, "wrong_submit": 0, "success_submit": 1},
            "nc": {"inputs": 3, "hello_ok": 1, "auth_attempt": 1, "bad_auth": 0, "malformed": 0, "flag_found": 1},
            "ssh": {"commands": ["pwd", "ls -la", "find /home -maxdepth 3 -type f 2>/dev/null", "grep -R \"flag\\|token\\|secret\" /home 2>/dev/null | head"], "flag_attempt": 1, "flag_found": 1},
            "survey": {
                "usability_score": 4,
                "challenge_quality_score": 5,
                "recommendation_quality_score": 5,
                "confidence_improvement_score": 5,
                "favorite_part": "ใช้คำแนะนำเดิมแล้วทำให้แก้โจทย์ได้เร็วขึ้น",
                "improvement_point": "อยากมีหน้าสรุปสิ่งที่ควรฝึกต่อเป็นลำดับขั้น",
                "comments": "รอบสามทำแบบมีแผนและรู้ว่าจะอ่านอะไรต่อก่อนกด solve",
            },
        },
    },
    "mint_s": {
        1: {
            "theme": "cautious_baseline",
            "web": {"requests": 8, "probes": 1, "login_fail": 2, "wrong_submit": 1, "success_submit": 0},
            "nc": {"inputs": 3, "hello_ok": 0, "auth_attempt": 1, "bad_auth": 2, "malformed": 1, "flag_found": 0},
            "ssh": {"commands": ["pwd", "ls -la"], "flag_attempt": 0, "flag_found": 0},
            "survey": {
                "usability_score": 4,
                "challenge_quality_score": 4,
                "recommendation_quality_score": 3,
                "confidence_improvement_score": 2,
                "favorite_part": "ชอบที่ระบบมีหลาย challenge style",
                "improvement_point": "ใช้เวลาสำรวจนานเกินไปก่อนลงมือจริง",
                "comments": "ยังไม่มั่นใจเวลาต้องตัดสินใจ submit",
            },
        },
        2: {
            "theme": "more_decisive",
            "web": {"requests": 7, "probes": 2, "login_fail": 1, "wrong_submit": 1, "success_submit": 1},
            "nc": {"inputs": 4, "hello_ok": 1, "auth_attempt": 2, "bad_auth": 1, "malformed": 0, "flag_found": 1},
            "ssh": {"commands": ["pwd", "ls -la", "find /home -maxdepth 2 -type f 2>/dev/null"], "flag_attempt": 1, "flag_found": 0},
            "survey": {
                "usability_score": 4,
                "challenge_quality_score": 5,
                "recommendation_quality_score": 4,
                "confidence_improvement_score": 4,
                "favorite_part": "คำแนะนำช่วยให้รู้ว่าควรตัดทิศทางไหนทิ้ง",
                "improvement_point": "ยังต้องฝึก multi-step exploitation ฝั่ง SSH",
                "comments": "รอบนี้กล้าตัดสินใจมากขึ้นและเริ่ม solve ได้บางโจทย์",
            },
        },
        3: {
            "theme": "confident_execution",
            "web": {"requests": 6, "probes": 1, "login_fail": 0, "wrong_submit": 0, "success_submit": 1},
            "nc": {"inputs": 3, "hello_ok": 1, "auth_attempt": 1, "bad_auth": 0, "malformed": 0, "flag_found": 1},
            "ssh": {"commands": ["pwd", "ls -la", "find /home -maxdepth 3 -type f 2>/dev/null", "cat /home/player/.bash_history 2>/dev/null"], "flag_attempt": 1, "flag_found": 1},
            "survey": {
                "usability_score": 5,
                "challenge_quality_score": 5,
                "recommendation_quality_score": 5,
                "confidence_improvement_score": 5,
                "favorite_part": "เริ่มเห็นว่าคำแนะนำ AI เชื่อมกับพฤติกรรมตัวเองจริง",
                "improvement_point": "อยากได้ recommendation ที่เจาะจง command sequence มากขึ้น",
                "comments": "พอรู้ข้อผิดพลาดเดิมแล้ว รอบสามจึงเล่นได้มั่นใจและครบกว่าเดิม",
            },
        },
    },
    "oak_s": {
        1: {
            "theme": "protocol_first",
            "web": {"requests": 2, "probes": 1, "login_fail": 2, "wrong_submit": 0, "success_submit": 0},
            "nc": {"inputs": 4, "hello_ok": 1, "auth_attempt": 2, "bad_auth": 1, "malformed": 0, "flag_found": 1},
            "ssh": {"commands": ["pwd", "ls"], "flag_attempt": 0, "flag_found": 0},
            "survey": {
                "usability_score": 3,
                "challenge_quality_score": 4,
                "recommendation_quality_score": 3,
                "confidence_improvement_score": 3,
                "favorite_part": "ถนัดโจทย์ protocol มากที่สุด",
                "improvement_point": "โจทย์ web กับ ssh ยังไม่ค่อยรู้จะเริ่มอย่างไร",
                "comments": "รอบแรกชัดเลยว่าถนัด protocol แต่ยัง imbalance",
            },
        },
        2: {
            "theme": "broader_skillset",
            "web": {"requests": 5, "probes": 2, "login_fail": 2, "wrong_submit": 1, "success_submit": 1},
            "nc": {"inputs": 4, "hello_ok": 1, "auth_attempt": 1, "bad_auth": 1, "malformed": 0, "flag_found": 1},
            "ssh": {"commands": ["pwd", "ls -la", "find /home -maxdepth 2 -type f 2>/dev/null"], "flag_attempt": 1, "flag_found": 0},
            "survey": {
                "usability_score": 4,
                "challenge_quality_score": 4,
                "recommendation_quality_score": 4,
                "confidence_improvement_score": 4,
                "favorite_part": "คำแนะนำทำให้เริ่มซ้อมโจทย์ที่ไม่ถนัดได้ชัดขึ้น",
                "improvement_point": "ยังต้องพัฒนา pivot และ post-exploitation",
                "comments": "รอบสองพยายามบาลานซ์ web/ssh มากขึ้น ไม่เน้น protocol อย่างเดียว",
            },
        },
        3: {
            "theme": "balanced_strength",
            "web": {"requests": 6, "probes": 1, "login_fail": 1, "wrong_submit": 0, "success_submit": 1},
            "nc": {"inputs": 3, "hello_ok": 1, "auth_attempt": 1, "bad_auth": 0, "malformed": 0, "flag_found": 1},
            "ssh": {"commands": ["pwd", "ls -la", "find /home -maxdepth 3 -type f 2>/dev/null", "grep -R \"flag\\|key\\|note\" /home 2>/dev/null | head"], "flag_attempt": 1, "flag_found": 1},
            "survey": {
                "usability_score": 4,
                "challenge_quality_score": 5,
                "recommendation_quality_score": 5,
                "confidence_improvement_score": 5,
                "favorite_part": "เห็นชัดว่าพอปรับตามคำแนะนำแล้วความสมดุลดีขึ้น",
                "improvement_point": "อยากให้ AI มีคำแนะนำต่อยอดเชิงลึกหลังรอบสาม",
                "comments": "รอบสามทำได้ครบทั้ง web, protocol และ ssh มากขึ้นอย่างเห็นได้ชัด",
            },
        },
    },
}


def log(message: str) -> None:
    print(message, flush=True)


def sleep_brief(low: float = 0.15, high: float = 0.45) -> None:
    time.sleep(random.uniform(low, high) * PAUSE_SCALE)


def load_cohort_rows(participant_filter: set[str] | None, min_round: int, max_round: int) -> List[RoundUser]:
    rows: List[RoundUser] = []
    with COHORT_CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            participant_id = row["participant_id"].strip()
            round_number = int(row["round_number"])
            if participant_filter and participant_id not in participant_filter:
                continue
            if round_number < min_round or round_number > max_round:
                continue
            rows.append(
                RoundUser(
                    participant_id=participant_id,
                    participant_name=row["participant_name"].strip(),
                    round_number=round_number,
                    username=row["username"].strip(),
                    notes=row.get("notes", "").strip(),
                )
            )
    rows.sort(key=lambda item: (item.participant_id, item.round_number))
    return rows


def http_get(path: str, params: Dict[str, Any] | None = None) -> Any:
    response = requests.get(f"{ORCH_BASE}/{path.lstrip('/')}", params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def http_post(path: str, payload: Dict[str, Any]) -> Any:
    response = requests.post(f"{ORCH_BASE}/{path.lstrip('/')}", json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def start_session(username: str, challenge_id: str) -> Dict[str, Any]:
    return http_get("start", {"user": username, "challenge": challenge_id})


def stop_session(session_id: str) -> None:
    try:
        http_get("stop", {"session_id": session_id})
    except Exception as exc:
        log(f"    [!] stop failed for {session_id}: {exc}")


def post_event(username: str, challenge_id: str, session_id: str, event_type: str, payload: Dict[str, Any] | None = None) -> None:
    http_post(
        "event_json",
        {
            "event_type": event_type,
            "user_key": username,
            "challenge_id": challenge_id,
            "session_id": session_id,
            "payload": payload or {},
        },
    )


def post_common_ui_events(username: str, challenge_id: str, session_id: str) -> None:
    post_event(username, challenge_id, session_id, "CHALLENGE_OPEN_UI")
    sleep_brief()
    post_event(username, challenge_id, session_id, "START_INSTANCE_UI_CLICK")
    sleep_brief()
    post_event(username, challenge_id, session_id, "INSTANCE_READY_UI")
    sleep_brief()


def request_session_feedback(session_id: str) -> None:
    try:
        http_get("feedback", {"session_id": session_id})
    except Exception as exc:
        log(f"    [!] feedback generation failed for {session_id}: {exc}")


def submit_participant_feedback(username: str, survey: Dict[str, Any]) -> None:
    payload = {"user_key": username, **survey}
    http_post("participant_feedback", payload)


def generate_user_report(username: str) -> Dict[str, Any]:
    response = requests.post(f"{ORCH_BASE}/generate_report/{username}", timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def get_existing_report(username: str) -> Optional[Dict[str, Any]]:
    """
    Best-effort check to avoid re-generating reports and hitting AI rate limits.
    """
    try:
        r = requests.get(f"{ORCH_BASE}/report/{username}", timeout=REQUEST_TIMEOUT)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _http_status_from_exc(exc: Exception) -> Optional[int]:
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        return exc.response.status_code
    return None


def generate_user_report_with_backoff(username: str, max_attempts: int = 6) -> Optional[Dict[str, Any]]:
    """
    Generate report but tolerate transient Gemini 429s by backing off.
    Returns None if it still fails after retries.
    """
    base_sleep = 6.0
    for attempt in range(1, max_attempts + 1):
        try:
            return generate_user_report(username)
        except Exception as exc:
            status = _http_status_from_exc(exc)
            is_rate_limited = status == 429
            is_5xx = status is not None and 500 <= status <= 599
            should_retry = is_rate_limited or is_5xx

            if not should_retry or attempt == max_attempts:
                log(f"    [!] generate_report failed user={username} attempt={attempt}/{max_attempts}: {exc}")
                return None

            sleep_s = (base_sleep * (2 ** (attempt - 1))) * random.uniform(0.85, 1.25) * max(0.5, PAUSE_SCALE)
            reason = "rate_limited" if is_rate_limited else f"http_{status}"
            log(f"    [*] generate_report retry user={username} attempt={attempt}/{max_attempts} reason={reason} sleep={sleep_s:.1f}s")
            time.sleep(sleep_s)


def simulate_web_round(user: RoundUser, plan: Dict[str, Any]) -> None:
    info = start_session(user.username, CHALLENGE_WEB)
    session_id = info["session_id"]
    log(f"    [web] {user.username} -> {session_id}")

    try:
        post_common_ui_events(user.username, CHALLENGE_WEB, session_id)
        for index in range(plan["requests"]):
            path = ["/", "/login", "/docs", "/api/status", "/help"][index % 5]
            post_event(user.username, CHALLENGE_WEB, session_id, "WEB_REQUEST", {"path": path})
            sleep_brief()

        for _ in range(plan["probes"]):
            post_event(user.username, CHALLENGE_WEB, session_id, "WEB_PROBE", {"path": "/api/auth"})
            sleep_brief()

        for _ in range(plan["login_fail"]):
            post_event(user.username, CHALLENGE_WEB, session_id, "LOGIN_FAIL", {"reason": "incorrect_password"})
            sleep_brief()

        for _ in range(plan["wrong_submit"]):
            post_event(
                user.username,
                CHALLENGE_WEB,
                session_id,
                "FLAG_SUBMIT_RESULT",
                {"result": "wrong", "response_excerpt": "incorrect flag"},
            )
            sleep_brief()

        for _ in range(plan["success_submit"]):
            post_event(
                user.username,
                CHALLENGE_WEB,
                session_id,
                "FLAG_SUBMIT_RESULT",
                {"result": "submitted", "response_excerpt": "correct solves"},
            )
            sleep_brief()

        request_session_feedback(session_id)
    finally:
        stop_session(session_id)


def simulate_nc_round(user: RoundUser, plan: Dict[str, Any]) -> None:
    info = start_session(user.username, CHALLENGE_NC)
    session_id = info["session_id"]
    log(f"    [nc] {user.username} -> {session_id}")

    try:
        post_common_ui_events(user.username, CHALLENGE_NC, session_id)
        post_event(user.username, CHALLENGE_NC, session_id, "TCP_CONNECT", {"host": info.get("host"), "port": info.get("port")})
        sleep_brief()

        for _ in range(plan["inputs"]):
            post_event(user.username, CHALLENGE_NC, session_id, "TCP_INPUT", {"message": "PING"})
            sleep_brief()

        for _ in range(plan["hello_ok"]):
            post_event(user.username, CHALLENGE_NC, session_id, "TCP_HELLO_OK", {"message": "HELLO OK"})
            sleep_brief()

        for _ in range(plan["auth_attempt"]):
            post_event(user.username, CHALLENGE_NC, session_id, "TCP_AUTH_ATTEMPT", {"token": "candidate"})
            sleep_brief()

        for _ in range(plan["bad_auth"]):
            post_event(user.username, CHALLENGE_NC, session_id, "TCP_BAD_AUTH", {"reason": "invalid_token"})
            sleep_brief()

        for _ in range(plan["malformed"]):
            post_event(user.username, CHALLENGE_NC, session_id, "TCP_MALFORMED", {"payload": "\\x00\\x01"})
            sleep_brief()

        for _ in range(plan["flag_found"]):
            post_event(user.username, CHALLENGE_NC, session_id, "FLAG_FOUND", {"source": "protocol"})
            sleep_brief()

        request_session_feedback(session_id)
    finally:
        stop_session(session_id)


def simulate_ssh_round(user: RoundUser, plan: Dict[str, Any]) -> None:
    info = start_session(user.username, CHALLENGE_SSH)
    session_id = info["session_id"]
    log(f"    [ssh] {user.username} -> {session_id}")

    try:
        post_common_ui_events(user.username, CHALLENGE_SSH, session_id)

        for command in plan["commands"]:
            post_event(user.username, CHALLENGE_SSH, session_id, "SSH_COMMAND", {"cmd": command})
            sleep_brief()

        for _ in range(plan["flag_attempt"]):
            post_event(user.username, CHALLENGE_SSH, session_id, "SSH_FLAG_ATTEMPT", {"path": "/home/player/flag.txt"})
            sleep_brief()

        for _ in range(plan["flag_found"]):
            post_event(user.username, CHALLENGE_SSH, session_id, "FLAG_FOUND", {"source": "ssh"})
            sleep_brief()

        request_session_feedback(session_id)
    finally:
        stop_session(session_id)


def run_round_user(user: RoundUser) -> None:
    plan = STUDY_PROFILES[user.participant_id][user.round_number]
    log(f"\n=== {user.participant_name} | {user.username} | round {user.round_number} | {plan['theme']} ===")

    simulate_web_round(user, plan["web"])
    sleep_brief(0.8, 1.4)
    simulate_nc_round(user, plan["nc"])
    sleep_brief(0.8, 1.4)
    simulate_ssh_round(user, plan["ssh"])
    sleep_brief(0.8, 1.4)

    submit_participant_feedback(user.username, plan["survey"])
    existing = get_existing_report(user.username)
    if existing and existing.get("skill_report") and existing.get("ai_report"):
        log("    [report] already exists (skill+ai) -> skip generate_report")
        return

    report_result = generate_user_report_with_backoff(user.username)
    if report_result is None:
        log("    [report] skipped (generation failed after retries)")
        return

    log(
        "    [report] "
        f"user={user.username} skill_report_id={report_result.get('skill_report_id')} "
        f"ai_report_id={report_result.get('ai_report_id')}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulate the round comparison study cohort.")
    parser.add_argument(
        "--participant",
        action="append",
        dest="participants",
        help="participant_id to simulate (repeatable), e.g. bank_s",
    )
    parser.add_argument(
        "--max-round",
        type=int,
        default=3,
        choices=[1, 2, 3],
        help="maximum round number to execute",
    )
    parser.add_argument(
        "--min-round",
        type=int,
        default=1,
        choices=[1, 2, 3],
        help="minimum round number to execute (inclusive)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    random.seed(RANDOM_SEED)

    if args.min_round > args.max_round:
        raise SystemExit("--min-round must be <= --max-round")

    participant_filter = set(args.participants or [])
    cohort_rows = load_cohort_rows(participant_filter if participant_filter else None, args.min_round, args.max_round)

    if not cohort_rows:
        raise SystemExit("No cohort rows matched the requested filters.")

    log(f"Starting round comparison study simulation via {ORCH_BASE}")
    log(f"Cohort source: {COHORT_CSV}")
    log(f"rounds: {args.min_round}-{args.max_round}  report_gap={REPORT_GAP_SECONDS}s")

    for index, user in enumerate(cohort_rows):
        run_round_user(user)
        if index < len(cohort_rows) - 1 and REPORT_GAP_SECONDS > 0:
            time.sleep(REPORT_GAP_SECONDS)

    log("\nSimulation finished.")
    log("Next step:")
    log("  Open http://ctf.100.113.75.64.nip.io/admin-round-comparison")


if __name__ == "__main__":
    main()
