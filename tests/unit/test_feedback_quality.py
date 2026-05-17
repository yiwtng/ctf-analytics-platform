"""

pytestmark = pytest.mark.unit

Tests for AI feedback quality assessment (G3).
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock
import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "platform", "orchestrator"))

from app.validation_service import FeedbackRating, _cohens_kappa

# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

_STORE: list[dict] = []


@pytest.fixture(autouse=True)
def reset():
    _STORE.clear()
    yield
    _STORE.clear()


def _fake_store_fb(r: FeedbackRating) -> None:
    key = (r.rater_id, r.participant_code, r.round_no)
    if not any((x["rater_id"], x["participant_code"], x["round_no"]) == key for x in _STORE):
        _STORE.append({
            "rater_id": r.rater_id, "participant_code": r.participant_code,
            "round_no": r.round_no, "relevance": r.relevance,
            "actionability": r.actionability, "accuracy": r.accuracy,
            "comment": r.comment,
        })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStoreAndRetrieve:
    def test_store_and_summary(self):
        """Stored ratings must appear in summary."""
        from app import validation_service as vs

        ratings = [
            FeedbackRating("E01", "P001", 1, 4, 5, 4),
            FeedbackRating("E02", "P001", 1, 3, 4, 5),
        ]
        mock_cur = MagicMock()
        mock_cur.__enter__ = lambda s: s
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_cur.fetchall.return_value = [
            {"rater_id": r.rater_id, "participant_code": r.participant_code,
             "round_no": r.round_no, "relevance": r.relevance,
             "actionability": r.actionability, "accuracy": r.accuracy}
            for r in ratings
        ]
        mock_conn = MagicMock()
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cur

        with patch.object(vs, "store_feedback_rating", side_effect=_fake_store_fb), \
             patch.object(vs, "_get_conn", return_value=mock_conn):
            for r in ratings:
                vs.store_feedback_rating(r)
            result = vs.feedback_quality_summary()

        assert result["n_ratings"] == 2
        assert "relevance" in result
        assert result["relevance"]["mean"] > 0

    def test_idempotent(self):
        """Duplicate store must not add second row."""
        from app import validation_service as vs

        r = FeedbackRating("E01", "P001", 1, 4, 4, 4)
        with patch.object(vs, "store_feedback_rating", side_effect=_fake_store_fb):
            vs.store_feedback_rating(r)
            vs.store_feedback_rating(r)
        assert len(_STORE) == 1


class TestConstraints:
    def test_relevance_zero_raises(self):
        """Score of 0 must fail validation."""
        from app import validation_service as vs
        with pytest.raises(ValueError):
            vs.store_feedback_rating(FeedbackRating("E01", "P001", 1, 0, 3, 3))

    def test_relevance_six_raises(self):
        """Score of 6 must fail validation."""
        from app import validation_service as vs
        with pytest.raises(ValueError):
            vs.store_feedback_rating(FeedbackRating("E01", "P001", 1, 6, 3, 3))

    def test_valid_boundary_values(self):
        """Scores 1 and 5 must be accepted."""
        from app import validation_service as vs
        mock_cur = MagicMock()
        mock_cur.__enter__ = lambda s: s
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn = MagicMock()
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cur

        with patch.object(vs, "_get_conn", return_value=mock_conn):
            vs.store_feedback_rating(FeedbackRating("E01", "P001", 1, 1, 5, 1))


class TestCohensKappa:
    def test_perfect_agreement(self):
        """Identical ratings → kappa == 1.0."""
        import numpy as np
        a = np.array([3, 4, 5, 3, 4])
        kappa = _cohens_kappa(a, a)
        assert abs(kappa - 1.0) < 1e-9

    def test_chance_agreement(self):
        """Kappa should be ≤ 1.0 always."""
        import numpy as np
        rng = np.random.default_rng(0)
        a = rng.integers(1, 6, 20)
        b = rng.integers(1, 6, 20)
        kappa = _cohens_kappa(a, b)
        assert kappa <= 1.0

    def test_known_kappa(self):
        """Verify kappa on a hand-computed example."""
        import numpy as np
        # Both rate as [5, 4, 3, 5, 4, 3] → perfect → kappa = 1
        a = np.array([5, 4, 3, 5, 4, 3])
        b = np.array([5, 4, 3, 5, 4, 3])
        assert abs(_cohens_kappa(a, b) - 1.0) < 1e-6


class TestQualitySummary:
    def test_mean_calculation(self):
        """Mean of [4, 5] = 4.5."""
        from app import validation_service as vs

        rows = [
            {"rater_id": "E01", "participant_code": "P001", "round_no": 1,
             "relevance": 4, "actionability": 5, "accuracy": 4},
            {"rater_id": "E02", "participant_code": "P001", "round_no": 1,
             "relevance": 5, "actionability": 5, "accuracy": 5},
        ]
        mock_cur = MagicMock()
        mock_cur.__enter__ = lambda s: s
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_cur.fetchall.return_value = rows
        mock_conn = MagicMock()
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cur

        with patch.object(vs, "_get_conn", return_value=mock_conn):
            result = vs.feedback_quality_summary()

        assert result["relevance"]["mean"] == 4.5
        assert result["relevance"]["pct_ge_4"] == 100.0
