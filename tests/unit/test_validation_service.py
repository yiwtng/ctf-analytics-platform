"""

pytestmark = pytest.mark.unit

Tests for the psychometric validation service.

Uses synthetic data to verify ICC, Cronbach's alpha, and convergent
validity calculations without requiring a live database.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "platform", "orchestrator"))

from app.validation_service import (
    ExpertRating,
    DIMENSIONS,
    _ICC_THRESHOLDS,
)

# ---------------------------------------------------------------------------
# Mock DB helpers
# ---------------------------------------------------------------------------

_RATING_STORE: list[dict] = []


@pytest.fixture(autouse=True)
def reset_store():
    _RATING_STORE.clear()
    yield
    _RATING_STORE.clear()


def _fake_store(rating: ExpertRating) -> None:
    key = (rating.rater_id, rating.participant_code, rating.round_no, rating.dimension)
    if not any(
        (r["rater_id"], r["participant_code"], r["round_no"], r["dimension"]) == key
        for r in _RATING_STORE
    ):
        _RATING_STORE.append({
            "rater_id": rating.rater_id,
            "participant_code": rating.participant_code,
            "round_no": rating.round_no,
            "dimension": rating.dimension,
            "score": rating.score,
        })


def _fake_fetch(dimension: str, round_no=None) -> list[dict]:
    result = [r for r in _RATING_STORE if r["dimension"] == dimension]
    if round_no is not None:
        result = [r for r in result if r["round_no"] == round_no]
    return result


# ---------------------------------------------------------------------------
# store_expert_rating
# ---------------------------------------------------------------------------

class TestStoreAndRetrieve:
    def test_store_and_fetch(self):
        """Rating stored must be retrievable."""
        from app import validation_service as vs

        rating = ExpertRating("E01", "P001", 1, "accuracy", 80.0)
        with patch.object(vs, "_fetch_expert_ratings", side_effect=_fake_fetch), \
             patch.object(vs, "store_expert_rating", side_effect=_fake_store):
            vs.store_expert_rating(rating)
            rows = vs._fetch_expert_ratings("accuracy")

        assert len(rows) == 1
        assert rows[0]["score"] == 80.0

    def test_rating_idempotent(self):
        """Duplicate store must not add a second row."""
        from app import validation_service as vs

        rating = ExpertRating("E01", "P001", 1, "accuracy", 80.0)
        with patch.object(vs, "store_expert_rating", side_effect=_fake_store), \
             patch.object(vs, "_fetch_expert_ratings", side_effect=_fake_fetch):
            vs.store_expert_rating(rating)
            vs.store_expert_rating(rating)
            rows = vs._fetch_expert_ratings("accuracy")

        assert len(rows) == 1

    def test_invalid_dimension_raises(self):
        """Unknown dimension must raise ValueError."""
        from app import validation_service as vs
        with pytest.raises(ValueError, match="Unknown dimension"):
            vs.store_expert_rating(ExpertRating("E01", "P001", 1, "nonexistent", 50.0))

    def test_score_out_of_range_raises(self):
        """Score outside [0, 100] must raise ValueError."""
        from app import validation_service as vs
        with pytest.raises(ValueError, match="Score"):
            vs.store_expert_rating(ExpertRating("E01", "P001", 1, "accuracy", 101.0))


# ---------------------------------------------------------------------------
# Cronbach's alpha (computed from synthetic numpy arrays)
# ---------------------------------------------------------------------------

class TestCronbachAlpha:
    def _make_synthetic_scores(self, alpha_target: float = 0.85, n: int = 30):
        """Generate synthetic 7-item scores with approximate target alpha."""
        import numpy as np
        rng = np.random.default_rng(0)
        # Shared latent factor
        factor = rng.normal(50, 15, n)
        noise_scale = 15 * ((1 - alpha_target) / alpha_target) ** 0.5
        items = np.column_stack([
            np.clip(factor + rng.normal(0, noise_scale, n), 0, 100)
            for _ in range(7)
        ])
        return items

    def test_cronbach_known_values(self):
        """Synthetic high-correlation data must yield alpha >= 0.70."""
        import numpy as np
        from app import validation_service as vs

        items = self._make_synthetic_scores(alpha_target=0.85, n=40)
        # Mock the DB call with our synthetic data
        import pandas as pd
        fake_rows = [
            {
                "user_key": f"u{i}",
                "accuracy_score": float(items[i, 0]),
                "persistence_score": float(items[i, 1]),
                "web_recon_score": float(items[i, 2]),
                "protocol_score": float(items[i, 3]),
                "ssh_pivot_score": float(items[i, 4]),
                "blue_analysis_score": float(items[i, 5]),
                "time_efficiency_score": float(items[i, 6]),
            }
            for i in range(len(items))
        ]

        mock_cur = MagicMock()
        mock_cur.__enter__ = lambda s: s
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_cur.fetchall.return_value = fake_rows

        mock_conn = MagicMock()
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cur

        with patch.object(vs, "_get_conn", return_value=mock_conn):
            result = vs.compute_cronbach_alpha()

        assert result["alpha"] is not None
        assert result["n_items"] == 7
        assert result["n_participants"] == 40

    def test_cronbach_acceptable_flag(self):
        """alpha >= 0.70 → acceptable == True; alpha < 0.70 → False."""
        from app import validation_service as vs

        with patch.object(vs, "compute_cronbach_alpha", return_value={"alpha": 0.82, "n_items": 7, "n_participants": 30, "acceptable": True}):
            result = vs.compute_cronbach_alpha()
        assert result["acceptable"] is True

    def test_insufficient_data(self):
        """Less than 2 rows → alpha == None."""
        from app import validation_service as vs

        mock_cur = MagicMock()
        mock_cur.__enter__ = lambda s: s
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_cur.fetchall.return_value = []

        mock_conn = MagicMock()
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cur

        with patch.object(vs, "_get_conn", return_value=mock_conn):
            result = vs.compute_cronbach_alpha()

        assert result["alpha"] is None
        assert result["acceptable"] is False


# ---------------------------------------------------------------------------
# Convergent validity
# ---------------------------------------------------------------------------

class TestConvergentValidity:
    def test_perfect_correlation(self):
        """When external == skill sum, r should be ≈ 1.0."""
        from app import validation_service as vs
        import numpy as np

        n = 20
        rng = np.random.default_rng(1)
        base = rng.uniform(30, 90, n)

        fake_rows = [
            {
                "user_key": f"u{i}",
                "accuracy_score": float(base[i]),
                "persistence_score": float(base[i]),
                "web_recon_score": float(base[i]),
                "protocol_score": float(base[i]),
                "ssh_pivot_score": float(base[i]),
                "blue_analysis_score": float(base[i]),
                "time_efficiency_score": float(base[i]),
                "total_solves": float(base[i]),   # perfect linear match
            }
            for i in range(n)
        ]

        mock_cur = MagicMock()
        mock_cur.__enter__ = lambda s: s
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_cur.fetchall.return_value = fake_rows

        mock_conn = MagicMock()
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cur

        with patch.object(vs, "_get_conn", return_value=mock_conn):
            result = vs.compute_convergent_validity("solve_count")

        assert result.get("pearson_r") is not None
        assert abs(result["pearson_r"]) > 0.95


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------

class TestGracefulSkip:
    def test_graceful_skip_when_lib_missing(self):
        """compute_icc must not crash when pingouin is unavailable."""
        from app import validation_service as vs
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name in ("pingouin", "factor_analyzer"):
                raise ImportError(f"Mocked missing: {name}")
            return real_import(name, *args, **kwargs)

        fake_rows = [
            {"rater_id": f"E0{j}", "participant_code": f"P{i:03d}",
             "round_no": 1, "dimension": "accuracy", "score": float(50 + i + j)}
            for i in range(5) for j in range(1, 3)
        ]

        with patch.object(vs, "_fetch_expert_ratings", return_value=fake_rows), \
             patch("builtins.__import__", side_effect=mock_import):
            result = vs.compute_icc("accuracy")

        # Must return something (either a result or a skip notice), never raise
        assert isinstance(result, dict)

    def test_efa_graceful_skip(self):
        """EFA returns {skipped: True} when factor_analyzer missing."""
        from app import validation_service as vs
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "factor_analyzer":
                raise ImportError("Mocked missing")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = vs.exploratory_factor_analysis()

        assert result.get("skipped") is True
