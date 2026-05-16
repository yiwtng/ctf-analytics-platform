import json
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Tuple

import psycopg2
import psycopg2.extras


ANALYTICS_DB_HOST = os.getenv("ANALYTICS_DB_HOST", "localhost")
ANALYTICS_DB_PORT = int(os.getenv("ANALYTICS_DB_PORT", "5432"))
ANALYTICS_DB_NAME = os.getenv("ANALYTICS_DB_NAME", "analytics")
ANALYTICS_DB_USER = os.getenv("ANALYTICS_DB_USER", "analytics")
ANALYTICS_DB_PASSWORD = os.getenv("ANALYTICS_DB_PASSWORD", "analytics")

OUTPUT_JSON = os.getenv("OUTPUT_JSON", "").strip()

RED_CHALLENGES = {
    "red_ghost_login",
    "red_protocol_probe",
    "red_pivot_notes",
    "red_log_poisoning",
}

TARGET_EVENTS = {
    "LOGIN_UI",
    "CHALLENGE_OPEN_UI",
    "START_INSTANCE_UI_CLICK",
    "INSTANCE_READY_UI",
    "START_INSTANCE_FAILED",
    "FLAG_SUBMIT_UI",
    "FLAG_SUBMIT_RESULT",
    "FLAG_SUBMIT_ERROR",
    "CHALLENGE_GIVE_UP",
    "CHALLENGE_INTERACTION_ERROR",
    "SESSION_START",
    "SESSION_STOP",
    "WEB_REQUEST",
    "SSH_COMMAND",
    "TCP_INPUT",
    "TCP_CONNECT",
    "TCP_BAD_AUTH",
    "TCP_MALFORMED",
    "TCP_HELLO_OK",
    "FLAG_FOUND",
}


def db_connect():
    return psycopg2.connect(
        host=ANALYTICS_DB_HOST,
        port=ANALYTICS_DB_PORT,
        dbname=ANALYTICS_DB_NAME,
        user=ANALYTICS_DB_USER,
        password=ANALYTICS_DB_PASSWORD,
    )


def fetch_events() -> List[Dict[str, Any]]:
    sql = """
        SELECT
            ts,
            event_type,
            user_key,
            challenge_id,
            session_id,
            payload
        FROM events
        WHERE event_type = ANY(%s)
        ORDER BY ts ASC
    """
    with db_connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (list(TARGET_EVENTS),))
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def empty_stats() -> Dict[str, Any]:
    return {
        "challenge_open_ui": 0,
        "start_click": 0,
        "instance_ready": 0,
        "start_failed": 0,
        "submit_ui": 0,
        "submit_wrong": 0,
        "submit_submitted": 0,
        "submit_unknown": 0,
        "submit_error": 0,
        "give_up": 0,
        "interaction_error": 0,
        "login_ui": 0,
        "session_start": 0,
        "flag_found": 0,
        "web_request": 0,
        "ssh_command": 0,
        "tcp_input": 0,
        "tcp_connect": 0,
        "tcp_bad_auth": 0,
        "tcp_malformed": 0,
        "tcp_hello_ok": 0,
        "session_ids": set(),
        "first_ts": None,
        "last_ts": None,
    }


def update_time_bucket(bucket: Dict[str, Any], ts):
    if bucket["first_ts"] is None or ts < bucket["first_ts"]:
        bucket["first_ts"] = ts
    if bucket["last_ts"] is None or ts > bucket["last_ts"]:
        bucket["last_ts"] = ts


def classify_user_challenge(stats: Dict[str, Any], challenge_id: str) -> str:
    wrong = stats["submit_wrong"]
    solved = stats["submit_submitted"] > 0 or stats["flag_found"] > 0
    give_up = stats["give_up"] > 0
    start_click = stats["start_click"]
    interaction_error = stats["interaction_error"]
    malformed = stats["tcp_malformed"]
    bad_auth = stats["tcp_bad_auth"]
    web_req = stats["web_request"]
    ssh_cmd = stats["ssh_command"]

    if give_up and not solved:
        return "abandoned"

    if challenge_id == "red_protocol_probe":
        if solved and wrong <= 1 and malformed <= 1 and bad_auth <= 1:
            return "efficient_protocol_solver"
        if malformed >= 3 or bad_auth >= 2:
            return "protocol_struggling"
        if start_click >= 3 and not solved:
            return "protocol_retry_loop"

    if challenge_id == "red_ghost_login":
        if solved and web_req <= 5 and wrong <= 1:
            return "efficient_web_solver"
        if web_req >= 6 and wrong >= 1:
            return "web_explorer"
        if start_click >= 3 and not solved:
            return "web_retry_loop"

    if challenge_id == "red_pivot_notes":
        if solved and ssh_cmd <= 5 and wrong <= 1:
            return "efficient_ssh_solver"
        if interaction_error >= 2 and not solved:
            return "ssh_struggling"
        if start_click >= 3 and not solved:
            return "ssh_retry_loop"

    if challenge_id == "red_log_poisoning":
        if solved and web_req >= 3 and wrong <= 1:
            return "methodical_web_solver"
        if web_req >= 6 and wrong >= 1:
            return "trial_and_error_web"
        if start_click >= 3 and not solved:
            return "web_retry_loop"

    if solved and wrong == 0:
        return "clean_solver"
    if solved and wrong >= 2:
        return "retry_spammer"
    if interaction_error >= 2 and not solved:
        return "interaction_struggling"
    return "mixed"


def classify_user_overall(user_summary: Dict[str, Any]) -> str:
    total_wrong = 0
    total_solved = 0
    total_start = 0
    total_giveup = 0
    total_errors = 0

    for stats in user_summary["by_challenge"].values():
        total_wrong += stats["submit_wrong"]
        total_solved += int(stats["submit_submitted"] > 0 or stats["flag_found"] > 0)
        total_start += stats["start_click"]
        total_giveup += stats["give_up"]
        total_errors += stats["interaction_error"] + stats["submit_error"] + stats["start_failed"]

    if total_solved >= 3 and total_wrong <= 2 and total_errors <= 1:
        return "efficient"
    if total_wrong >= 4 and total_start >= 4:
        return "retry_spammer"
    if total_giveup >= 1 and total_solved <= 1:
        return "struggling"
    if total_errors >= 3 and total_solved <= 1:
        return "environment_or_interaction_issue"
    if total_solved >= 2 and total_wrong >= 2:
        return "persistent"
    return "mixed"


def analyze(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    per_user: Dict[str, Dict[str, Any]] = {}

    for row in events:
        event_type = row.get("event_type")
        user_key = row.get("user_key") or "unknown"
        challenge_id = row.get("challenge_id")
        session_id = row.get("session_id")
        ts = row.get("ts")
        payload = row.get("payload") or {}

        if challenge_id and challenge_id not in RED_CHALLENGES:
            continue

        if user_key not in per_user:
            per_user[user_key] = {
                "user_key": user_key,
                "by_challenge": defaultdict(empty_stats),
            }

        if challenge_id is None:
            # login หรือ event รวม user-level
            if event_type == "LOGIN_UI":
                for ch in per_user[user_key]["by_challenge"].values():
                    ch["login_ui"] += 1
            continue

        stats = per_user[user_key]["by_challenge"][challenge_id]
        update_time_bucket(stats, ts)

        if session_id:
            stats["session_ids"].add(session_id)

        if event_type == "CHALLENGE_OPEN_UI":
            stats["challenge_open_ui"] += 1
        elif event_type == "START_INSTANCE_UI_CLICK":
            stats["start_click"] += 1
        elif event_type == "INSTANCE_READY_UI":
            stats["instance_ready"] += 1
        elif event_type == "START_INSTANCE_FAILED":
            stats["start_failed"] += 1
        elif event_type == "FLAG_SUBMIT_UI":
            stats["submit_ui"] += 1
        elif event_type == "FLAG_SUBMIT_RESULT":
            result = (payload.get("result") or "unknown").lower()
            if result == "wrong":
                stats["submit_wrong"] += 1
            elif result == "submitted":
                stats["submit_submitted"] += 1
            else:
                stats["submit_unknown"] += 1
        elif event_type == "FLAG_SUBMIT_ERROR":
            stats["submit_error"] += 1
        elif event_type == "CHALLENGE_GIVE_UP":
            stats["give_up"] += 1
        elif event_type == "CHALLENGE_INTERACTION_ERROR":
            stats["interaction_error"] += 1
        elif event_type == "SESSION_START":
            stats["session_start"] += 1
        elif event_type == "FLAG_FOUND":
            stats["flag_found"] += 1
        elif event_type == "WEB_REQUEST":
            stats["web_request"] += 1
        elif event_type == "SSH_COMMAND":
            stats["ssh_command"] += 1
        elif event_type == "TCP_INPUT":
            stats["tcp_input"] += 1
        elif event_type == "TCP_CONNECT":
            stats["tcp_connect"] += 1
        elif event_type == "TCP_BAD_AUTH":
            stats["tcp_bad_auth"] += 1
        elif event_type == "TCP_MALFORMED":
            stats["tcp_malformed"] += 1
        elif event_type == "TCP_HELLO_OK":
            stats["tcp_hello_ok"] += 1

    final = {
        "users": [],
        "summary": {
            "user_count": 0,
            "challenge_count": len(RED_CHALLENGES),
        },
    }

    for user_key, user_summary in sorted(per_user.items()):
        output_user = {
            "user_key": user_key,
            "profile": "",
            "by_challenge": {},
        }

        for challenge_id, stats in sorted(user_summary["by_challenge"].items()):
            challenge_profile = classify_user_challenge(stats, challenge_id)

            output_user["by_challenge"][challenge_id] = {
                "profile": challenge_profile,
                "challenge_open_ui": stats["challenge_open_ui"],
                "start_click": stats["start_click"],
                "instance_ready": stats["instance_ready"],
                "start_failed": stats["start_failed"],
                "submit_ui": stats["submit_ui"],
                "submit_wrong": stats["submit_wrong"],
                "submit_submitted": stats["submit_submitted"],
                "submit_unknown": stats["submit_unknown"],
                "submit_error": stats["submit_error"],
                "give_up": stats["give_up"],
                "interaction_error": stats["interaction_error"],
                "session_start": stats["session_start"],
                "flag_found": stats["flag_found"],
                "web_request": stats["web_request"],
                "ssh_command": stats["ssh_command"],
                "tcp_input": stats["tcp_input"],
                "tcp_connect": stats["tcp_connect"],
                "tcp_bad_auth": stats["tcp_bad_auth"],
                "tcp_malformed": stats["tcp_malformed"],
                "tcp_hello_ok": stats["tcp_hello_ok"],
                "session_count": len(stats["session_ids"]),
                "first_ts": stats["first_ts"].isoformat() if stats["first_ts"] else None,
                "last_ts": stats["last_ts"].isoformat() if stats["last_ts"] else None,
            }

        output_user["profile"] = classify_user_overall(user_summary)
        final["users"].append(output_user)

    final["summary"]["user_count"] = len(final["users"])
    return final


def print_human_report(report: Dict[str, Any]):
    print("=" * 100)
    print("RED TEAM BEHAVIOR ANALYSIS")
    print("=" * 100)
    print(f"Users analyzed: {report['summary']['user_count']}")
    print(f"Challenges tracked: {report['summary']['challenge_count']}")
    print()

    for user in report["users"]:
        print(f"[USER] {user['user_key']}  -> overall profile: {user['profile']}")
        for challenge_id, stats in user["by_challenge"].items():
            print(f"  - {challenge_id}")
            print(f"      profile            : {stats['profile']}")
            print(f"      open/start/ready   : {stats['challenge_open_ui']}/{stats['start_click']}/{stats['instance_ready']}")
            print(f"      submit(w/s/u/e)    : {stats['submit_wrong']}/{stats['submit_submitted']}/{stats['submit_unknown']}/{stats['submit_error']}")
            print(f"      give_up/errors     : {stats['give_up']}/{stats['interaction_error']}")
            print(f"      sessions           : {stats['session_count']}")
            print(f"      web/ssh/tcp_input  : {stats['web_request']}/{stats['ssh_command']}/{stats['tcp_input']}")
            print(f"      bad_auth/malformed : {stats['tcp_bad_auth']}/{stats['tcp_malformed']}")
            print(f"      first/last         : {stats['first_ts']} -> {stats['last_ts']}")
        print()


def main():
    try:
        events = fetch_events()
    except Exception as exc:
        print(f"[!] Failed to fetch events: {exc}")
        sys.exit(1)

    report = analyze(events)
    print_human_report(report)

    if OUTPUT_JSON:
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"[+] JSON report written to: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()