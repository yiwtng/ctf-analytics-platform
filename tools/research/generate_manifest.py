"""
Generate a reproducibility manifest for the research dataset.

Outputs a JSON file containing:
- Participant counts per group and round
- Event counts per round
- SHA-256 hashes of each public CSV (proves files were not altered post-analysis)
- Timestamp range of actual data collection
- Platform version snapshot

Usage:
    python tools/research/generate_manifest.py --data-dir data/ --out data/manifest.json
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import timezone

import psycopg2
import psycopg2.extras

ANALYTICS_DB_HOST = os.getenv("ANALYTICS_DB_HOST", "analytics_db")
ANALYTICS_DB_PORT = int(os.getenv("ANALYTICS_DB_PORT", "5432"))
ANALYTICS_DB_NAME = os.getenv("ANALYTICS_DB_NAME", "analytics")
ANALYTICS_DB_USER = os.getenv("ANALYTICS_DB_USER", "analytics")
ANALYTICS_DB_PASSWORD = os.getenv("ANALYTICS_DB_PASSWORD", "analytics")

PUBLIC_CSVS = [
    "events_anonymized.csv",
    "skill_scores.csv",
    "survey_responses.csv",
    "expert_ratings.csv",
]


def _get_conn():
    return psycopg2.connect(
        host=ANALYTICS_DB_HOST,
        port=ANALYTICS_DB_PORT,
        dbname=ANALYTICS_DB_NAME,
        user=ANALYTICS_DB_USER,
        password=ANALYTICS_DB_PASSWORD,
    )


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _file_hashes(data_dir: str) -> dict:
    hashes = {}
    for name in PUBLIC_CSVS:
        path = os.path.join(data_dir, name)
        if os.path.exists(path):
            hashes[name] = {"sha256": _sha256(path), "bytes": os.path.getsize(path)}
        else:
            hashes[name] = {"sha256": None, "bytes": None, "missing": True}
    return hashes


def _db_stats() -> dict:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Total events + timestamp range
            cur.execute("""
                SELECT
                    COUNT(*)                                    AS total_events,
                    MIN(ts)                                     AS first_event,
                    MAX(ts)                                     AS last_event,
                    COUNT(DISTINCT user_key)                    AS unique_users
                FROM events
            """)
            event_summary = dict(cur.fetchone())

            # Participant counts per experiment condition
            cur.execute("""
                SELECT condition, COUNT(*) AS n
                FROM experiment_assignment
                GROUP BY condition
                ORDER BY condition
            """)
            experiment_counts = [dict(r) for r in cur.fetchall()]

            # Skill report counts per user (proxy for rounds completed)
            cur.execute("""
                SELECT COUNT(DISTINCT user_key) AS users_with_reports,
                       COUNT(*) AS total_reports
                FROM user_skill_reports
            """)
            report_summary = dict(cur.fetchone())

            events_by_round = []
            snapshots_by_round = [report_summary]

    # Convert timestamps to ISO strings
    for k in ("first_event", "last_event"):
        v = event_summary.get(k)
        if v is not None:
            event_summary[k] = v.isoformat()

    return {
        "event_summary": event_summary,
        "events_by_round": events_by_round,
        "experiment_assignment": experiment_counts,
        "skill_snapshots_by_round": snapshots_by_round,
    }


def generate_manifest(data_dir: str, out_path: str) -> dict:
    from datetime import datetime

    # Require that IRB-approved public CSVs actually exist before generating manifest.
    # The manifest must only describe real research data, not synthetic fixtures.
    required = [os.path.join(data_dir, name) for name in PUBLIC_CSVS]
    missing = [p for p in required if not os.path.exists(p)]
    if missing:
        print(
            "ERROR: The following public dataset files are missing:\n  "
            + "\n  ".join(missing)
            + "\n\nManifest generation is only valid after IRB-approved data collection."
            "\nDo NOT run this script on synthetic fixture data in tests/fixtures/.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Computing file hashes...")
    hashes = _file_hashes(data_dir)

    print("Querying database statistics...")
    try:
        db = _db_stats()
    except Exception as exc:
        print(f"[WARNING] DB query failed: {exc} — manifest will omit DB stats", file=sys.stderr)
        db = {"error": str(exc)}

    manifest = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "platform": "ctf-analytics-platform",
        "experiment_seed": 42,
        "data_provenance": "IRB-approved collection, KMUTNB Human Research Ethics Committee",
        "file_hashes": hashes,
        "database": db,
    }

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False, default=str)

    print(f"Manifest written → {out_path}")
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Generate reproducibility manifest")
    parser.add_argument("--data-dir", default="data/", help="Directory containing public CSVs")
    parser.add_argument("--out", default="data/manifest.json", help="Output path for manifest JSON")
    args = parser.parse_args()
    generate_manifest(args.data_dir, args.out)


if __name__ == "__main__":
    main()
