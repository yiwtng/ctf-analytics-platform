"""
Experiment assignment for the CTF skill-feedback study.

Implements block randomization to assign participants to control
(no AI feedback) or treatment (with AI feedback) conditions, with
balanced allocation within blocks to prevent group-size drift.

Block randomization guarantees that within every consecutive block of
`block_size` enrollments, exactly half are assigned to CONTROL and half
to TREATMENT. The ordering within each block is shuffled using a seeded
PRNG to ensure reproducibility.
"""

from __future__ import annotations

import datetime
import os
import random
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import psycopg2
import psycopg2.extras

ANALYTICS_DB_HOST = os.getenv("ANALYTICS_DB_HOST", "analytics_db")
ANALYTICS_DB_PORT = int(os.getenv("ANALYTICS_DB_PORT", "5432"))
ANALYTICS_DB_NAME = os.getenv("ANALYTICS_DB_NAME", "analytics")
ANALYTICS_DB_USER = os.getenv("ANALYTICS_DB_USER", "analytics")
ANALYTICS_DB_PASSWORD = os.getenv("ANALYTICS_DB_PASSWORD", "analytics")

# Default block size: 4 → 2 control + 2 treatment per block
DEFAULT_BLOCK_SIZE = int(os.getenv("EXPERIMENT_BLOCK_SIZE", "4"))
# Global seed for reproducibility; override via EXPERIMENT_SEED env var
DEFAULT_SEED = int(os.getenv("EXPERIMENT_SEED", "42"))


class Condition(str, Enum):
    CONTROL = "control"    # score-only, no skill report, no AI feedback
    TREATMENT = "treatment"  # full 7-dim skill report + LLM feedback


@dataclass
class Assignment:
    user_id: int
    condition: Condition
    block_id: int
    assigned_at: datetime.datetime
    seed: int


def _get_conn() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=ANALYTICS_DB_HOST,
        port=ANALYTICS_DB_PORT,
        dbname=ANALYTICS_DB_NAME,
        user=ANALYTICS_DB_USER,
        password=ANALYTICS_DB_PASSWORD,
    )


def _count_enrolled() -> int:
    """Return total number of already-assigned participants."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM experiment_assignment")
            return cur.fetchone()[0]


def _generate_block(block_id: int, block_size: int, seed: int) -> list[Condition]:
    """
    Generate one balanced block. Within a block of `block_size`,
    exactly half are CONTROL and half TREATMENT, shuffled with
    a deterministic seed derived from (seed, block_id).
    """
    half = block_size // 2
    conditions = [Condition.CONTROL] * half + [Condition.TREATMENT] * half
    rng = random.Random(seed ^ (block_id * 2654435761))  # per-block seed mixing
    rng.shuffle(conditions)
    return conditions


def assign_participant(
    user_id: int,
    *,
    block_size: int = DEFAULT_BLOCK_SIZE,
    seed: int | None = None,
) -> Assignment:
    """
    Assign a participant using block randomization.

    Within each block of `block_size`, exactly half go to CONTROL and
    half to TREATMENT. Blocks fill sequentially as participants enroll.
    Deterministic given `seed` for reproducibility.

    Raises:
        ValueError: if block_size is odd or < 2.
    """
    if block_size < 2 or block_size % 2 != 0:
        raise ValueError(f"block_size must be an even number >= 2, got {block_size}")

    effective_seed = seed if seed is not None else DEFAULT_SEED

    # Return existing assignment (idempotent)
    existing = get_assignment(user_id)
    if existing is not None:
        return existing

    enrolled = _count_enrolled()
    block_id = enrolled // block_size
    position_in_block = enrolled % block_size

    block = _generate_block(block_id, block_size, effective_seed)
    condition = block[position_in_block]
    now = datetime.datetime.now(tz=datetime.timezone.utc)

    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO experiment_assignment
                    (user_id, condition, block_id, seed, assigned_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO NOTHING
                """,
                (user_id, condition.value, block_id, effective_seed, now),
            )
        conn.commit()

    return Assignment(
        user_id=user_id,
        condition=condition,
        block_id=block_id,
        assigned_at=now,
        seed=effective_seed,
    )


def get_assignment(user_id: int) -> Optional[Assignment]:
    """Return existing assignment or None if not yet assigned."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM experiment_assignment WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()

    if row is None:
        return None

    return Assignment(
        user_id=row["user_id"],
        condition=Condition(row["condition"]),
        block_id=row["block_id"],
        assigned_at=row["assigned_at"],
        seed=row["seed"],
    )


def is_treatment(user_id: int) -> bool:
    """
    Feature-flag helper. Returns True only if the user is assigned to
    TREATMENT. Fail-safe: returns False for unassigned users to prevent
    AI report leakage into the control group.
    """
    assignment = get_assignment(user_id)
    if assignment is None:
        return False
    return assignment.condition == Condition.TREATMENT


def assignment_summary() -> dict:
    """
    Return allocation balance summary for monitoring during data collection.

    Returns:
        {'control': int, 'treatment': int, 'unassigned': int, 'balance_ok': bool}
    """
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT condition, COUNT(*) AS n
                FROM experiment_assignment
                GROUP BY condition
                """
            )
            rows = cur.fetchall()

    counts = {Condition.CONTROL: 0, Condition.TREATMENT: 0}
    for condition_val, n in rows:
        try:
            counts[Condition(condition_val)] = n
        except ValueError:
            pass

    control = counts[Condition.CONTROL]
    treatment = counts[Condition.TREATMENT]
    total = control + treatment
    balance_ok = abs(control - treatment) <= max(1, total // 10)  # ±10% tolerance

    return {
        "control": control,
        "treatment": treatment,
        "unassigned": 0,  # tracked externally via user roster
        "balance_ok": balance_ok,
    }
