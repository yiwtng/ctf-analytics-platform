"""
Pre-test and post-test assessment service.

Stores baseline (pre) and final (post) assessment scores for each enrolled
participant. Used to compute learning gain in the analysis pipeline.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

import psycopg2
import psycopg2.extras


ANALYTICS_DB_HOST = os.getenv("ANALYTICS_DB_HOST", "analytics_db")
ANALYTICS_DB_PORT = int(os.getenv("ANALYTICS_DB_PORT", "5432"))
ANALYTICS_DB_NAME = os.getenv("ANALYTICS_DB_NAME", "analytics")
ANALYTICS_DB_USER = os.getenv("ANALYTICS_DB_USER", "analytics")
ANALYTICS_DB_PASSWORD = os.getenv("ANALYTICS_DB_PASSWORD", "analytics")

VALID_ASSESSMENT_TYPES = {"pretest", "posttest"}


class AssessmentError(ValueError):
    """Raised on invalid assessment input."""


def _get_conn():
    return psycopg2.connect(
        host=ANALYTICS_DB_HOST,
        port=ANALYTICS_DB_PORT,
        dbname=ANALYTICS_DB_NAME,
        user=ANALYTICS_DB_USER,
        password=ANALYTICS_DB_PASSWORD,
    )


def _log(event_type: str, detail: dict[str, Any]) -> None:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO data_collection_log (round_no, event_type, detail) VALUES (%s, %s, %s)",
                (None, event_type, json.dumps(detail, default=str)),
            )


def record_assessment_score(
    *,
    participant_code: str,
    assessment_type: str,
    score: float,
    max_score: float,
    administered_at: datetime,
) -> dict[str, Any]:
    """Store a pre-test or post-test result. Each participant may have at most one
    record per assessment_type (enforced by UNIQUE constraint)."""
    if assessment_type not in VALID_ASSESSMENT_TYPES:
        raise AssessmentError(f"invalid assessment_type: {assessment_type}")
    if score < 0 or score > max_score:
        raise AssessmentError(f"score {score} out of range [0, {max_score}]")
    if max_score <= 0:
        raise AssessmentError("max_score must be > 0")

    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT 1 FROM participant_enrollment WHERE participant_code = %s",
                (participant_code,),
            )
            if not cur.fetchone():
                raise AssessmentError(
                    f"no enrollment record for {participant_code} — cannot record assessment"
                )

            cur.execute(
                """
                INSERT INTO participant_assessment
                  (participant_code, assessment_type, score, max_score, administered_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (participant_code, assessment_type) DO UPDATE
                  SET score = EXCLUDED.score,
                      max_score = EXCLUDED.max_score,
                      administered_at = EXCLUDED.administered_at
                RETURNING id, administered_at
                """,
                (participant_code, assessment_type, score, max_score, administered_at),
            )
            row = dict(cur.fetchone())

    _log("assessment_recorded", {
        "participant_code": participant_code,
        "assessment_type": assessment_type,
        "score": score,
        "max_score": max_score,
    })

    return {
        "id": row["id"],
        "participant_code": participant_code,
        "assessment_type": assessment_type,
        "score": score,
        "max_score": max_score,
        "administered_at": row["administered_at"],
    }


def get_assessment(participant_code: str, assessment_type: str) -> dict[str, Any] | None:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM participant_assessment "
                "WHERE participant_code = %s AND assessment_type = %s",
                (participant_code, assessment_type),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def compute_learning_gain(participant_code: str) -> dict[str, Any] | None:
    """Return (pretest_pct, posttest_pct, gain_pct) for a participant, or None if either missing."""
    pre = get_assessment(participant_code, "pretest")
    post = get_assessment(participant_code, "posttest")
    if not pre or not post:
        return None
    pre_pct = 100.0 * pre["score"] / pre["max_score"]
    post_pct = 100.0 * post["score"] / post["max_score"]
    return {
        "participant_code": participant_code,
        "pretest_pct": round(pre_pct, 2),
        "posttest_pct": round(post_pct, 2),
        "gain_pct": round(post_pct - pre_pct, 2),
    }
