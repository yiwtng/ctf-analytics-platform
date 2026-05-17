"""
Participant enrollment service.

Manages the full lifecycle from informed consent through completion or
withdrawal. All enrolled participants are required to pass the data
provenance gate before analysis.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import psycopg2
import psycopg2.extras

from app.experiment import assign_participant


ANALYTICS_DB_HOST = os.getenv("ANALYTICS_DB_HOST", "analytics_db")
ANALYTICS_DB_PORT = int(os.getenv("ANALYTICS_DB_PORT", "5432"))
ANALYTICS_DB_NAME = os.getenv("ANALYTICS_DB_NAME", "analytics")
ANALYTICS_DB_USER = os.getenv("ANALYTICS_DB_USER", "analytics")
ANALYTICS_DB_PASSWORD = os.getenv("ANALYTICS_DB_PASSWORD", "analytics")

TARGET_N = 70

VALID_SOURCE_GROUPS = {"military", "kmutnb", "ctf_community"}
VALID_AGE_RANGES = {"18-25", "26-35", "36+"}
VALID_EXPERIENCE_LEVELS = {"beginner", "intermediate", "advanced"}


class EnrollmentStatus(str, Enum):
    PENDING_CONSENT = "pending_consent"
    CONSENTED = "consented"
    PRE_TESTED = "pre_tested"
    ASSIGNED = "assigned"
    ACTIVE = "active"
    COMPLETED = "completed"
    WITHDRAWN = "withdrawn"


class EnrollmentError(ValueError):
    """Raised on enrollment validation failures (duplicates, bad values, etc.)."""


def _get_conn():
    return psycopg2.connect(
        host=ANALYTICS_DB_HOST,
        port=ANALYTICS_DB_PORT,
        dbname=ANALYTICS_DB_NAME,
        user=ANALYTICS_DB_USER,
        password=ANALYTICS_DB_PASSWORD,
    )


def _log(round_no: int | None, event_type: str, detail: dict[str, Any]) -> None:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO data_collection_log (round_no, event_type, detail) VALUES (%s, %s, %s)",
                (round_no, event_type, json.dumps(detail, default=str)),
            )


def enroll_participant(
    *,
    ctfd_user_id: int,
    participant_code: str,
    source_group: str,
    age_range: str,
    education_level: str,
    experience_level: str,
    consent_recorded_at: datetime,
    irb_study_id: str,
) -> dict[str, Any]:
    """Register a participant and assign them to an experiment condition.

    Raises EnrollmentError on invalid input or duplicate enrollment.
    Returns the assignment record on success.
    """
    if source_group not in VALID_SOURCE_GROUPS:
        raise EnrollmentError(f"invalid source_group: {source_group}")
    if age_range not in VALID_AGE_RANGES:
        raise EnrollmentError(f"invalid age_range: {age_range}")
    if experience_level not in VALID_EXPERIENCE_LEVELS:
        raise EnrollmentError(f"invalid experience_level: {experience_level}")
    if not participant_code or not participant_code.strip():
        raise EnrollmentError("participant_code is required")
    if not irb_study_id or not irb_study_id.strip():
        raise EnrollmentError("irb_study_id is required (no enrollment without IRB approval)")

    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT participant_code FROM participant_enrollment "
                "WHERE participant_code = %s OR ctfd_user_id = %s",
                (participant_code, ctfd_user_id),
            )
            if cur.fetchone():
                raise EnrollmentError(
                    f"duplicate enrollment for participant_code={participant_code} or ctfd_user_id={ctfd_user_id}"
                )

            cur.execute(
                """
                INSERT INTO participant_enrollment
                  (participant_code, ctfd_user_id, source_group, age_range,
                   education_level, experience_level, irb_study_id,
                   consent_recorded, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING participant_code, enrolled_at
                """,
                (
                    participant_code, ctfd_user_id, source_group, age_range,
                    education_level, experience_level, irb_study_id,
                    consent_recorded_at, EnrollmentStatus.CONSENTED.value,
                ),
            )
            _ = cur.fetchone()

    assignment = assign_participant(ctfd_user_id)

    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE participant_enrollment SET status = %s WHERE participant_code = %s",
                (EnrollmentStatus.ASSIGNED.value, participant_code),
            )

    _log(None, "enrollment", {
        "participant_code": participant_code,
        "ctfd_user_id": ctfd_user_id,
        "source_group": source_group,
        "condition": assignment["condition"],
        "irb_study_id": irb_study_id,
    })

    return {
        "participant_code": participant_code,
        "ctfd_user_id": ctfd_user_id,
        "condition": assignment["condition"],
        "block_id": assignment["block_id"],
        "status": EnrollmentStatus.ASSIGNED.value,
    }


def update_enrollment_status(
    participant_code: str,
    new_status: EnrollmentStatus | str,
    detail: dict[str, Any] | None = None,
) -> None:
    status = new_status.value if isinstance(new_status, EnrollmentStatus) else new_status

    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE participant_enrollment SET status = %s WHERE participant_code = %s",
                (status, participant_code),
            )
            if cur.rowcount == 0:
                raise EnrollmentError(f"no enrollment record for {participant_code}")

    _log(None, "status_update", {
        "participant_code": participant_code,
        "new_status": status,
        "detail": detail or {},
    })


def record_withdrawal(
    participant_code: str,
    reason: str | None = None,
    delete_data: bool = False,
) -> None:
    """Record voluntary withdrawal. If delete_data=True, anonymize related records (PDPA right to erasure)."""
    now = datetime.now(tz=timezone.utc)
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE participant_enrollment
                SET status = %s, withdrawn_at = %s
                WHERE participant_code = %s
                """,
                (EnrollmentStatus.WITHDRAWN.value, now, participant_code),
            )
            if cur.rowcount == 0:
                raise EnrollmentError(f"no enrollment record for {participant_code}")

            if delete_data:
                # Anonymize related records — keep audit trail but remove identifiers
                cur.execute(
                    "DELETE FROM participant_assessment WHERE participant_code = %s",
                    (participant_code,),
                )

    _log(None, "withdrawal", {
        "participant_code": participant_code,
        "reason": reason or "not specified",
        "data_erased": delete_data,
    })


def get_study_dashboard() -> dict[str, Any]:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT COUNT(*) AS n FROM participant_enrollment")
            total = cur.fetchone()["n"]

            cur.execute("""
                SELECT ea.condition, COUNT(*) AS n
                FROM participant_enrollment pe
                JOIN experiment_assignment ea ON pe.ctfd_user_id = ea.user_id
                GROUP BY ea.condition
            """)
            by_condition = {r["condition"]: r["n"] for r in cur.fetchall()}
            by_condition.setdefault("control", 0)
            by_condition.setdefault("treatment", 0)

            cur.execute(
                "SELECT source_group, COUNT(*) AS n FROM participant_enrollment GROUP BY source_group"
            )
            by_source = {r["source_group"]: r["n"] for r in cur.fetchall()}

            cur.execute(
                "SELECT status, COUNT(*) AS n FROM participant_enrollment GROUP BY status"
            )
            by_status = {r["status"]: r["n"] for r in cur.fetchall()}

    return {
        "total_enrolled": total,
        "by_condition": by_condition,
        "by_source": by_source,
        "by_status": by_status,
        "target_n": TARGET_N,
        "recruitment_progress_pct": round(100.0 * total / TARGET_N, 1) if TARGET_N else 0.0,
    }


def get_enrollment(participant_code: str) -> dict[str, Any] | None:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM participant_enrollment WHERE participant_code = %s",
                (participant_code,),
            )
            row = cur.fetchone()
    return dict(row) if row else None
