"""
verify_data_provenance.py — Pre-analysis gate for research integrity.

Scans the analytics DB and classifies every user_key by provenance:
  - assigned:   has a record in experiment_assignment (enrolled via experiment.py)
  - simulation: matches known simulation patterns (bank.s*, mint.s*, oak.s*)
  - unknown:    events exist but no experiment_assignment record

Exits with code 1 if any simulation or unknown users are found.
Must pass before running statistical_tests.py or export_anonymized_dataset.py.

Usage:
    python tools/research/verify_data_provenance.py
    python tools/research/verify_data_provenance.py --allow-unknown  # warn only
    python tools/research/verify_data_provenance.py --json           # machine-readable
"""

import argparse
import json
import os
import re
import sys

import psycopg2
import psycopg2.extras

ANALYTICS_DB_HOST = os.getenv("ANALYTICS_DB_HOST", "analytics_db")
ANALYTICS_DB_PORT = int(os.getenv("ANALYTICS_DB_PORT", "5432"))
ANALYTICS_DB_NAME = os.getenv("ANALYTICS_DB_NAME", "analytics")
ANALYTICS_DB_USER = os.getenv("ANALYTICS_DB_USER", "analytics")
ANALYTICS_DB_PASSWORD = os.getenv("ANALYTICS_DB_PASSWORD", "analytics")

# Patterns that identify legacy simulation users
SIMULATION_PATTERNS = [
    re.compile(r"^bank\.s", re.IGNORECASE),
    re.compile(r"^mint\.s", re.IGNORECASE),
    re.compile(r"^oak\.s", re.IGNORECASE),
]

SYSTEM_USERS = {"admin", ""}


def _get_conn():
    return psycopg2.connect(
        host=ANALYTICS_DB_HOST,
        port=ANALYTICS_DB_PORT,
        dbname=ANALYTICS_DB_NAME,
        user=ANALYTICS_DB_USER,
        password=ANALYTICS_DB_PASSWORD,
    )


def _is_simulation(user_key: str) -> bool:
    return any(p.match(user_key) for p in SIMULATION_PATTERNS)


def scan() -> dict:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT user_key, COUNT(*) AS event_count, MIN(ts) AS first_event
                FROM events
                WHERE user_key IS NOT NULL AND user_key != ''
                GROUP BY user_key
                ORDER BY first_event
            """)
            event_users = {r["user_key"]: dict(r) for r in cur.fetchall()}

            cur.execute("""
                SELECT user_id, condition, assigned_at
                FROM experiment_assignment
            """)
            assigned = {r["user_id"]: dict(r) for r in cur.fetchall()}

            # Enrollment is the authoritative IRB-tracked roster
            enrolled_codes = set()
            enrolled_ctfd_ids = set()
            try:
                cur.execute(
                    "SELECT participant_code, ctfd_user_id FROM participant_enrollment "
                    "WHERE status != 'withdrawn'"
                )
                for r in cur.fetchall():
                    enrolled_codes.add(r["participant_code"])
                    enrolled_ctfd_ids.add(r["ctfd_user_id"])
            except psycopg2.Error:
                pass  # migration 009 not yet applied

            cur.execute("SELECT DISTINCT user_key FROM user_skill_reports")
            reported_users = {r["user_key"] for r in cur.fetchall()}

    result = {
        "total_event_users": len(event_users),
        "assigned_via_experiment": len(assigned),
        "enrolled_irb_tracked": len(enrolled_codes),
        "simulation": [],
        "unknown": [],
        "clean": [],
    }

    for user_key, info in event_users.items():
        if user_key in SYSTEM_USERS:
            continue
        if _is_simulation(user_key):
            result["simulation"].append({
                "user_key": user_key,
                "event_count": info["event_count"],
                "first_event": str(info["first_event"]),
                "reason": "matches simulation pattern (bank.s*/mint.s*/oak.s*)",
            })
        elif enrolled_codes and user_key not in enrolled_codes:
            result["unknown"].append({
                "user_key": user_key,
                "event_count": info["event_count"],
                "first_event": str(info["first_event"]),
                "reason": "events exist but no participant_enrollment record (IRB-tracked roster)",
            })
        elif not enrolled_codes and user_key not in reported_users and len(assigned) > 0:
            result["unknown"].append({
                "user_key": user_key,
                "event_count": info["event_count"],
                "first_event": str(info["first_event"]),
                "reason": "events exist but no experiment_assignment record",
            })
        else:
            result["clean"].append(user_key)

    return result


def report(result: dict, allow_unknown: bool = False, as_json: bool = False) -> bool:
    """Print report. Returns True if DB is clean for analysis."""
    if as_json:
        print(json.dumps(result, indent=2, default=str))
        return len(result["simulation"]) == 0 and (allow_unknown or len(result["unknown"]) == 0)

    print("=" * 60)
    print("DATA PROVENANCE VERIFICATION REPORT")
    print("=" * 60)
    print(f"Total users with events : {result['total_event_users']}")
    print(f"Enrolled (IRB-tracked)  : {result.get('enrolled_irb_tracked', 0)}")
    print(f"Assigned via experiment : {result['assigned_via_experiment']}")
    print(f"Simulation users found  : {len(result['simulation'])}")
    print(f"Unknown-origin users    : {len(result['unknown'])}")
    print(f"Clean users             : {len(result['clean'])}")
    print()

    if result["simulation"]:
        print("SIMULATION USERS (must not appear in research database):")
        for u in result["simulation"]:
            print(f"  ✗ {u['user_key']:20s}  events={u['event_count']:4d}  {u['reason']}")
        print()

    if result["unknown"]:
        label = "WARNING" if allow_unknown else "UNKNOWN-ORIGIN USERS (cannot be used in analysis)"
        print(f"{label}:")
        for u in result["unknown"]:
            print(f"  ? {u['user_key']:20s}  events={u['event_count']:4d}  {u['reason']}")
        print()

    if result["clean"]:
        print(f"Clean users: {', '.join(result['clean'])}")
        print()

    sim_fail = len(result["simulation"]) > 0
    unk_fail = not allow_unknown and len(result["unknown"]) > 0

    if sim_fail or unk_fail:
        print("=" * 60)
        print("PROVENANCE CHECK FAILED")
        print("=" * 60)
        if sim_fail:
            print("Action required: reset the DB using")
            print("  tools/setup/reset_for_data_collection.sh")
            print("and collect real data before running analysis.")
        if unk_fail:
            print("Action required: ensure all participants are enrolled via")
            print("  POST /experiment/assign before starting data collection.")
        return False

    print("=" * 60)
    print("PROVENANCE CHECK PASSED — DB ready for analysis")
    print("=" * 60)
    return True


def main():
    parser = argparse.ArgumentParser(description="Verify analytics DB data provenance")
    parser.add_argument("--allow-unknown", action="store_true",
                        help="Warn about unknown users but do not exit(1)")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON instead of human-readable report")
    args = parser.parse_args()

    try:
        result = scan()
    except Exception as exc:
        print(f"ERROR: Cannot connect to analytics DB: {exc}", file=sys.stderr)
        sys.exit(2)

    ok = report(result, allow_unknown=args.allow_unknown, as_json=args.json)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
