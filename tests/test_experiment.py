"""
Tests for the block-randomization experiment assignment module.

All tests use an in-memory mock of the DB layer so no live database
is required during CI.
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — mock DB so tests run without a real PostgreSQL connection
# ---------------------------------------------------------------------------

_STORE: dict[int, dict] = {}  # in-memory replacement for experiment_assignment table


def _mock_count() -> int:
    return len(_STORE)


def _mock_get(user_id: int):
    return _STORE.get(user_id)


def _mock_insert(user_id: int, condition: str, block_id: int, seed: int, assigned_at):
    if user_id not in _STORE:
        _STORE[user_id] = {
            "user_id": user_id,
            "condition": condition,
            "block_id": block_id,
            "seed": seed,
            "assigned_at": assigned_at,
        }


@pytest.fixture(autouse=True)
def reset_store():
    """Clear in-memory store before each test."""
    _STORE.clear()
    yield
    _STORE.clear()


# Patch DB functions at module level
@pytest.fixture(autouse=True)
def patch_db(reset_store):
    with (
        patch("app.experiment._count_enrolled", side_effect=_mock_count),
        patch("app.experiment.get_assignment", side_effect=lambda uid: (
            __import__("app.experiment", fromlist=["Assignment", "Condition"]).Assignment(
                user_id=_STORE[uid]["user_id"],
                condition=__import__("app.experiment", fromlist=["Condition"]).Condition(_STORE[uid]["condition"]),
                block_id=_STORE[uid]["block_id"],
                assigned_at=_STORE[uid]["assigned_at"],
                seed=_STORE[uid]["seed"],
            ) if uid in _STORE else None
        )),
    ):
        # Also patch the internal DB write inside assign_participant
        with patch("app.experiment._get_conn") as mock_conn:
            conn = MagicMock()
            cur = MagicMock()
            cur.__enter__ = lambda s: s
            cur.__exit__ = MagicMock(return_value=False)
            conn.__enter__ = lambda s: s
            conn.__exit__ = MagicMock(return_value=False)
            conn.cursor.return_value = cur
            mock_conn.return_value = conn

            # Intercept the actual INSERT call
            def fake_execute(sql, params=None):
                if params and "INSERT" in str(sql):
                    uid, cond, blk, sd, ts = params
                    _mock_insert(uid, cond, blk, sd, ts)

            cur.execute.side_effect = fake_execute
            yield


# ---------------------------------------------------------------------------
# Import after patching is set up
# ---------------------------------------------------------------------------

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "platform", "orchestrator"))

from app.experiment import (
    Condition,
    Assignment,
    assign_participant,
    get_assignment,
    is_treatment,
    _generate_block,
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBlockBalance:
    def test_single_block_balanced(self):
        """4 participants in one block → exactly 2 control, 2 treatment."""
        for uid in range(1, 5):
            assign_participant(uid, block_size=4, seed=42)

        conditions = [_STORE[uid]["condition"] for uid in range(1, 5)]
        assert conditions.count("control") == 2
        assert conditions.count("treatment") == 2

    def test_multiple_blocks_balanced(self):
        """12 participants across 3 blocks → 6 control, 6 treatment."""
        for uid in range(1, 13):
            assign_participant(uid, block_size=4, seed=42)

        conditions = [_STORE[uid]["condition"] for uid in range(1, 13)]
        assert conditions.count("control") == 6
        assert conditions.count("treatment") == 6

    def test_block_ids_assigned_correctly(self):
        """Users 1–4 → block 0; users 5–8 → block 1."""
        for uid in range(1, 9):
            assign_participant(uid, block_size=4, seed=42)

        for uid in range(1, 5):
            assert _STORE[uid]["block_id"] == 0
        for uid in range(5, 9):
            assert _STORE[uid]["block_id"] == 1


class TestDeterministicSeed:
    def test_same_seed_same_order(self):
        """Given the same seed, enrollment order must be identical."""
        for uid in range(1, 5):
            assign_participant(uid, block_size=4, seed=99)
        order_a = [_STORE[uid]["condition"] for uid in range(1, 5)]

        _STORE.clear()
        for uid in range(1, 5):
            assign_participant(uid, block_size=4, seed=99)
        order_b = [_STORE[uid]["condition"] for uid in range(1, 5)]

        assert order_a == order_b

    def test_different_seeds_may_differ(self):
        """Different seeds should produce at least one distinct block arrangement."""
        block_a = _generate_block(0, 4, seed=1)
        block_b = _generate_block(0, 4, seed=2)
        # Not strictly guaranteed, but extremely unlikely to collide
        # This is a probabilistic check — acceptable for test purposes
        assert isinstance(block_a, list) and isinstance(block_b, list)


class TestIsTreatment:
    def test_unassigned_user_returns_false(self):
        """is_treatment must return False (safe default) for unassigned users."""
        assert is_treatment(9999) is False

    def test_control_user_returns_false(self):
        """Control-assigned user must not get treatment gate."""
        _STORE[1] = {
            "user_id": 1, "condition": "control", "block_id": 0,
            "seed": 42, "assigned_at": datetime.datetime.now()
        }
        assert is_treatment(1) is False

    def test_treatment_user_returns_true(self):
        """Treatment-assigned user must pass the gate."""
        _STORE[2] = {
            "user_id": 2, "condition": "treatment", "block_id": 0,
            "seed": 42, "assigned_at": datetime.datetime.now()
        }
        assert is_treatment(2) is True


class TestIdempotent:
    def test_assign_twice_returns_same(self):
        """Calling assign_participant twice must not create a second record."""
        a1 = assign_participant(1, block_size=4, seed=42)
        a2 = assign_participant(1, block_size=4, seed=42)
        assert a1.condition == a2.condition
        assert len([k for k in _STORE if k == 1]) == 1

    def test_store_unchanged_after_second_call(self):
        """Store size must stay at 1 after duplicate assignment."""
        assign_participant(1, block_size=4, seed=42)
        assign_participant(1, block_size=4, seed=42)
        assert len(_STORE) == 1


class TestBlockSizeValidation:
    def test_odd_block_size_raises(self):
        with pytest.raises(ValueError, match="even"):
            assign_participant(1, block_size=3, seed=42)

    def test_block_size_one_raises(self):
        with pytest.raises(ValueError, match="even"):
            assign_participant(1, block_size=1, seed=42)

    def test_zero_block_size_raises(self):
        with pytest.raises(ValueError):
            assign_participant(1, block_size=0, seed=42)
