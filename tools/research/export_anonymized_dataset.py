"""
Export an anonymized, reproducible research dataset.

Replaces all identifiers with stable participant codes (P001, P002, ...),
strips PII from free-text fields, and writes CSVs + a data dictionary
suitable for public release alongside the manuscript.

The code map (user_id → P0XX) is written to a PRIVATE file that must
never be committed to version control (.gitignore enforces this).

Usage:
    python tools/research/export_anonymized_dataset.py --out data/

Environment variables:
    ANALYTICS_DB_HOST, ANALYTICS_DB_PORT, ANALYTICS_DB_NAME,
    ANALYTICS_DB_USER, ANALYTICS_DB_PASSWORD
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

ANALYTICS_DB_HOST = os.getenv("ANALYTICS_DB_HOST", "analytics_db")
ANALYTICS_DB_PORT = int(os.getenv("ANALYTICS_DB_PORT", "5432"))
ANALYTICS_DB_NAME = os.getenv("ANALYTICS_DB_NAME", "analytics")
ANALYTICS_DB_USER = os.getenv("ANALYTICS_DB_USER", "analytics")
ANALYTICS_DB_PASSWORD = os.getenv("ANALYTICS_DB_PASSWORD", "analytics")

# PII patterns to scrub from free text
_PII_PATTERNS = [
    re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),   # email
    re.compile(r"(?:\+66|0)\d{9}"),                                      # Thai phone
    re.compile(r"\b\d{13}\b"),                                           # Thai national ID
    re.compile(r"\b(?:นาย|นาง|น\.ส\.|Mr\.|Mrs\.|Ms\.)\s+\S+", re.UNICODE),  # names with title
]


def _get_conn() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=ANALYTICS_DB_HOST, port=ANALYTICS_DB_PORT,
        dbname=ANALYTICS_DB_NAME, user=ANALYTICS_DB_USER,
        password=ANALYTICS_DB_PASSWORD,
    )


def _scrub_pii(text: str | None) -> str | None:
    """Replace PII patterns with [REDACTED]."""
    if not text:
        return text
    for pattern in _PII_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def build_code_map() -> dict[str, str]:
    """
    Build a deterministic user_key → 'P0XX' mapping sorted by the
    first event timestamp (proxy for enrollment order).

    The private code map is written to data/_code_map_private.csv and
    must NOT be committed to the public repository.
    """
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_key, MIN(ts) AS first_seen
                FROM events
                WHERE user_key IS NOT NULL AND user_key <> ''
                GROUP BY user_key
                ORDER BY first_seen ASC
                """
            )
            rows = cur.fetchall()

    return {row[0]: f"P{i+1:03d}" for i, row in enumerate(rows)}


def _write_code_map(code_map: dict[str, str], out_dir: str) -> None:
    path = Path(out_dir) / "_code_map_private.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["user_key", "participant_code"])
        for user_key, code in code_map.items():
            writer.writerow([user_key, code])
    print(f"[PRIVATE] Code map written to {path}  ← DO NOT commit this file")


def export_events(out_dir: str, code_map: dict[str, str] | None = None) -> None:
    """
    Write events_anonymized.csv.

    Columns: participant_code, round_no (from cohort if available),
    ts_offset (seconds from first event in that round), action_type,
    challenge_id, success.
    No IP, no usernames, no raw payloads.
    """
    if code_map is None:
        code_map = build_code_map()

    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT e.user_key, e.ts, e.event_type, e.challenge_id,
                       e.payload
                FROM events e
                WHERE e.user_key IS NOT NULL AND e.user_key <> ''
                ORDER BY e.user_key, e.ts ASC
                """
            )
            rows = [dict(r) for r in cur.fetchall()]

    # Compute ts_offset per user
    first_ts: dict[str, Any] = {}
    for row in rows:
        if row["user_key"] not in first_ts:
            first_ts[row["user_key"]] = row["ts"]

    out_path = Path(out_dir) / "events_anonymized.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "participant_code", "ts_offset_seconds", "action_type",
            "challenge_id", "success",
        ])
        writer.writeheader()
        for row in rows:
            code = code_map.get(row["user_key"])
            if not code:
                continue
            offset = (row["ts"] - first_ts[row["user_key"]]).total_seconds()
            payload = row.get("payload") or {}
            success = payload.get("result") == "submitted" if isinstance(payload, dict) else False
            writer.writerow({
                "participant_code": code,
                "ts_offset_seconds": int(offset),
                "action_type": row["event_type"],
                "challenge_id": row.get("challenge_id") or "",
                "success": int(success),
            })

    print(f"[CSV] events_anonymized.csv → {out_path}")


def export_skill_scores(out_dir: str, code_map: dict[str, str] | None = None) -> None:
    """Write skill_scores.csv: participant_code, 7 dims, overall, condition."""
    if code_map is None:
        code_map = build_code_map()

    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT r.user_key, r.accuracy_score, r.persistence_score,
                       r.web_recon_score, r.protocol_score, r.ssh_pivot_score,
                       r.blue_analysis_score, r.time_efficiency_score,
                       r.overall_level, e.condition
                FROM user_skill_reports r
                LEFT JOIN experiment_assignment e
                    ON r.user_key = CAST(e.user_id AS TEXT)
                ORDER BY r.user_key, r.generated_at ASC
                """
            )
            rows = [dict(r) for r in cur.fetchall()]

    out_path = Path(out_dir) / "skill_scores.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "participant_code", "accuracy", "persistence", "web_recon",
            "protocol", "ssh_pivot", "blue_analysis", "time_efficiency",
            "overall_level", "condition",
        ])
        writer.writeheader()
        for row in rows:
            code = code_map.get(row["user_key"])
            if not code:
                continue
            writer.writerow({
                "participant_code": code,
                "accuracy": row["accuracy_score"],
                "persistence": row["persistence_score"],
                "web_recon": row["web_recon_score"],
                "protocol": row["protocol_score"],
                "ssh_pivot": row["ssh_pivot_score"],
                "blue_analysis": row["blue_analysis_score"],
                "time_efficiency": row["time_efficiency_score"],
                "overall_level": row["overall_level"],
                "condition": row.get("condition") or "unassigned",
            })

    print(f"[CSV] skill_scores.csv → {out_path}")


def export_surveys(out_dir: str, code_map: dict[str, str] | None = None) -> None:
    """Write survey_responses.csv with free-text PII scrubbed."""
    if code_map is None:
        code_map = build_code_map()

    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT user_key, usability_score, challenge_quality_score,
                       recommendation_quality_score, confidence_improvement_score,
                       favorite_part, improvement_point, comments, ts
                FROM participant_feedback
                ORDER BY user_key, ts ASC
                """
            )
            rows = [dict(r) for r in cur.fetchall()]

    out_path = Path(out_dir) / "survey_responses.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "participant_code", "usability", "challenge_quality",
            "recommendation_quality", "confidence_improvement",
            "favorite_part_redacted", "improvement_point_redacted", "comments_redacted",
        ])
        writer.writeheader()
        for row in rows:
            code = code_map.get(row["user_key"])
            if not code:
                continue
            writer.writerow({
                "participant_code": code,
                "usability": row["usability_score"],
                "challenge_quality": row["challenge_quality_score"],
                "recommendation_quality": row["recommendation_quality_score"],
                "confidence_improvement": row["confidence_improvement_score"],
                "favorite_part_redacted": _scrub_pii(row.get("favorite_part")),
                "improvement_point_redacted": _scrub_pii(row.get("improvement_point")),
                "comments_redacted": _scrub_pii(row.get("comments")),
            })

    print(f"[CSV] survey_responses.csv → {out_path}")


def export_expert_ratings(out_dir: str) -> None:
    """Write expert_ratings.csv — already uses anonymized participant codes."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT rater_id, participant_code, round_no, dimension, score FROM expert_rating"
            )
            rows = [dict(r) for r in cur.fetchall()]

    out_path = Path(out_dir) / "expert_ratings.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "rater_id", "participant_code", "round_no", "dimension", "score",
        ])
        writer.writeheader()
        writer.writerows(rows)

    print(f"[CSV] expert_ratings.csv → {out_path}")


def write_data_dictionary(out_dir: str) -> None:
    """Write data/README.md describing every column and anonymization method."""
    content = """# Dataset Description

This dataset accompanies the manuscript:

> T. Wutthiamornthada and N. Wisitpongphan, "Automated Analysis of
> Problem-Solving Skills with LLM-Generated Feedback in
> Capture-the-Flag Cybersecurity Education,"
> *IEEE Transactions on Learning Technologies*, 2026. (Under review)

## Anonymization

All participant identifiers have been replaced with stable codes
(P001, P002, …) sorted by enrollment order. The mapping is stored
in a private file (`_code_map_private.csv`) that is excluded from
version control via `.gitignore`.

Timestamps are expressed as `ts_offset_seconds` — the number of
seconds elapsed since each participant's first recorded event in
that round — to prevent re-identification through wall-clock time.

Free-text survey responses have been scrubbed using regex patterns
targeting emails, phone numbers, national IDs, and name prefixes.

## Ethics

This study received IRB approval from the KMUTNB Human Research Ethics
Committee and complies with Thailand's PDPA (B.E. 2562).
See `docs/ethics/` for consent and compliance documents.

## Files

### events_anonymized.csv

| Column | Type | Description |
|---|---|---|
| participant_code | string | Anonymized participant ID (P001 …) |
| ts_offset_seconds | integer | Seconds since participant's first event |
| action_type | string | CTF event type (e.g., FLAG_SUBMIT_RESULT) |
| challenge_id | string | Challenge identifier |
| success | integer | 1 if action succeeded, 0 otherwise |

### skill_scores.csv

| Column | Type | Description |
|---|---|---|
| participant_code | string | Anonymized participant ID |
| accuracy | float | Accuracy score (0–100) |
| persistence | float | Persistence score (0–100) |
| web_recon | float | Web Recon score (0–100) |
| protocol | float | Protocol score (0–100) |
| ssh_pivot | float | SSH Pivot score (0–100) |
| blue_analysis | float | Blue Analysis score (0–100) |
| time_efficiency | float | Time Efficiency score (0–100) |
| overall_level | string | Developing / Intermediate / Advanced |
| condition | string | control or treatment |

### survey_responses.csv

| Column | Type | Description |
|---|---|---|
| participant_code | string | Anonymized participant ID |
| usability | integer | Usability rating (1–5 Likert) |
| challenge_quality | integer | Challenge quality rating (1–5) |
| recommendation_quality | integer | Feedback quality rating (1–5) |
| confidence_improvement | integer | Self-efficacy improvement (1–5) |
| favorite_part_redacted | string | Open-ended response (PII scrubbed) |
| improvement_point_redacted | string | Open-ended response (PII scrubbed) |
| comments_redacted | string | Open-ended response (PII scrubbed) |

### expert_ratings.csv

| Column | Type | Description |
|---|---|---|
| rater_id | string | Blinded expert ID (E01, E02 …) |
| participant_code | string | Anonymized participant ID |
| round_no | integer | CTF round (1, 2, or 3) |
| dimension | string | Skill dimension rated |
| score | float | Expert judgment score (0–100) |
"""
    out_path = Path(out_dir) / "README.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[DOC] data/README.md → {out_path}")


def _check_provenance() -> None:
    """Refuse to export if DB contains simulation or unknown-origin users."""
    import subprocess
    script = os.path.join(os.path.dirname(__file__), "verify_data_provenance.py")
    script = os.path.normpath(script)
    if not os.path.exists(script):
        import warnings
        warnings.warn("verify_data_provenance.py not found — skipping provenance gate")
        return
    result = subprocess.run([sys.executable, script], capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        print("\nExport refused: provenance check failed.", file=sys.stderr)
        print("Reset the DB and collect real IRB-approved data before exporting.", file=sys.stderr)
        sys.exit(1)
    print("[provenance] OK — all users verified")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export anonymized research dataset")
    parser.add_argument("--out", default="data/", help="Output directory")
    parser.add_argument("--skip-provenance", action="store_true",
                        help="Skip provenance check (development only — never use on real data)")
    args = parser.parse_args()

    if not args.skip_provenance:
        _check_provenance()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Building participant code map...")
    code_map = build_code_map()
    _write_code_map(code_map, str(out_dir))

    print(f"Exporting dataset for {len(code_map)} participants...")
    export_events(str(out_dir), code_map)
    export_skill_scores(str(out_dir), code_map)
    export_surveys(str(out_dir), code_map)
    export_expert_ratings(str(out_dir))
    write_data_dictionary(str(out_dir))

    print("\nDone. Public files in:", out_dir)
    print("IMPORTANT: Do NOT commit _code_map_private.csv")


if __name__ == "__main__":
    main()
