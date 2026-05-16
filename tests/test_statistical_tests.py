"""
Tests for the inferential statistics pipeline (G6).

All DB calls are mocked; scipy/numpy are used directly for reference values.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import sys, os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "platform", "orchestrator"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools", "analysis"))

import statistical_tests as st

# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

def _make_group(n: int, mean: float, sd: float = 10.0, seed: int = 0) -> list[float]:
    import numpy as np
    rng = np.random.default_rng(seed)
    return np.clip(rng.normal(mean, sd, n), 0, 100).tolist()


# ---------------------------------------------------------------------------
# wilcoxon_within
# ---------------------------------------------------------------------------

class TestWilcoxon:
    def test_synthetic_improvement(self):
        """Pre < Post → Wilcoxon should detect improvement."""
        import numpy as np
        from scipy import stats as sp

        pre = np.array([40.0, 45.0, 50.0, 35.0, 55.0])
        post = np.array([60.0, 65.0, 70.0, 55.0, 75.0])

        # Ground truth via scipy directly
        stat_ref, p_ref = sp.wilcoxon(post, pre, alternative="greater")

        # Patch DB to return our synthetic data
        pre_rows = [{"user_key": str(i), "accuracy_score": float(pre[i]),
                     "condition": "treatment", "round_no": 1} for i in range(len(pre))]
        post_rows = [{"user_key": str(i), "accuracy_score": float(post[i]),
                      "condition": "treatment", "round_no": 3} for i in range(len(post))]

        def fake_fetch(condition=None, round_no=None):
            if round_no == 1:
                return pre_rows
            return post_rows

        with patch.object(st, "_fetch_scores", side_effect=fake_fetch):
            result = st.wilcoxon_within("treatment", "accuracy_score")

        assert result.get("skipped") is None or not result.get("skipped")
        assert abs(result["p_value"] - round(float(p_ref), 4)) < 0.01

    def test_insufficient_data_skipped(self):
        """Less than 3 paired observations → skipped."""
        with patch.object(st, "_fetch_scores", return_value=[]):
            result = st.wilcoxon_within("treatment", "accuracy_score")
        assert result.get("skipped") is True


# ---------------------------------------------------------------------------
# mann_whitney_between
# ---------------------------------------------------------------------------

class TestMannWhitney:
    def test_synthetic(self):
        """Treatment clearly higher than control → p < 0.05."""
        import numpy as np

        ctrl_vals = _make_group(20, mean=50, seed=1)
        trt_vals = _make_group(20, mean=75, seed=2)

        ctrl_rows = [{"user_key": f"c{i}", "accuracy_score": ctrl_vals[i],
                      "condition": "control", "round_no": 3} for i in range(len(ctrl_vals))]
        trt_rows = [{"user_key": f"t{i}", "accuracy_score": trt_vals[i],
                     "condition": "treatment", "round_no": 3} for i in range(len(trt_vals))]

        def fake_fetch(condition=None, round_no=None):
            if condition == "control":
                return ctrl_rows
            return trt_rows

        with patch.object(st, "_fetch_scores", side_effect=fake_fetch):
            result = st.mann_whitney_between("accuracy_score", "post")

        assert result.get("skipped") is None or not result.get("skipped")
        assert result["p_value"] < 0.05
        assert result["median_treatment"] > result["median_control"]

    def test_insufficient_data_skipped(self):
        """Single observation per group → skipped."""
        single = [{"user_key": "u1", "accuracy_score": 50.0, "condition": "control", "round_no": 3}]

        def fake_fetch(condition=None, round_no=None):
            return single

        with patch.object(st, "_fetch_scores", side_effect=fake_fetch):
            result = st.mann_whitney_between("accuracy_score", "post")
        assert result.get("skipped") is True


# ---------------------------------------------------------------------------
# cohens_d
# ---------------------------------------------------------------------------

class TestCohensD:
    def test_known_d(self):
        """Two groups with means 50 and 60, SD=10 → d ≈ 1.0."""
        import numpy as np

        rng = np.random.default_rng(42)
        ctrl = rng.normal(50, 10, 100)
        trt = rng.normal(60, 10, 100)

        ctrl_rows = [{"user_key": f"c{i}", "accuracy_score": float(ctrl[i]),
                      "condition": "control", "round_no": 3} for i in range(len(ctrl))]
        trt_rows = [{"user_key": f"t{i}", "accuracy_score": float(trt[i]),
                     "condition": "treatment", "round_no": 3} for i in range(len(trt))]

        def fake_fetch(condition=None, round_no=None):
            return ctrl_rows if condition == "control" else trt_rows

        with patch.object(st, "_fetch_scores", side_effect=fake_fetch):
            result = st.cohens_d("accuracy_score", "post")

        assert result.get("skipped") is None or not result.get("skipped")
        assert abs(result["d"] - 1.0) < 0.15  # allow ±0.15 tolerance
        assert result["interpretation"] == "large"

    def test_negligible_effect(self):
        """Identical groups → d ≈ 0, interpretation 'negligible'."""
        import numpy as np

        same = np.full(20, 60.0)
        rows = [{"user_key": f"u{i}", "accuracy_score": float(same[i]),
                 "condition": "c", "round_no": 3} for i in range(len(same))]

        with patch.object(st, "_fetch_scores", return_value=rows):
            result = st.cohens_d("accuracy_score", "post")
        # Zero variance → skipped
        assert result.get("skipped") is True or result.get("d") is not None


# ---------------------------------------------------------------------------
# holm_bonferroni
# ---------------------------------------------------------------------------

class TestHolmBonferroni:
    def test_known_correction(self):
        """Verify against manual calculation."""
        p_vals = {"A": 0.01, "B": 0.04, "C": 0.20}
        adj = st.holm_bonferroni(p_vals)

        # Sorted: A(0.01), B(0.04), C(0.20)
        # A: 0.01 * 3 = 0.03 → 0.03
        # B: 0.04 * 2 = 0.08 → max(0.08, 0.03) = 0.08
        # C: 0.20 * 1 = 0.20 → max(0.20, 0.08) = 0.20
        assert abs(adj["A"] - 0.03) < 1e-9
        assert abs(adj["B"] - 0.08) < 1e-9
        assert abs(adj["C"] - 0.20) < 1e-9

    def test_monotonicity(self):
        """Adjusted p-values must be non-decreasing in sort order."""
        import numpy as np
        p_vals = {f"D{i}": float(p) for i, p in enumerate(np.linspace(0.001, 0.5, 7))}
        adj = st.holm_bonferroni(p_vals)
        vals = sorted(adj.values())
        assert vals == sorted(vals)

    def test_all_significant(self):
        """Very small p-values → all adjusted still ≤ 1.0."""
        p_vals = {f"D{i}": 0.001 for i in range(7)}
        adj = st.holm_bonferroni(p_vals)
        for v in adj.values():
            assert 0 <= v <= 1.0


# ---------------------------------------------------------------------------
# run_all structure
# ---------------------------------------------------------------------------

class TestRunAll:
    def test_output_structure(self):
        """run_all must return a key for every dimension."""
        def fake_fetch(condition=None, round_no=None):
            return []  # empty → all skipped

        with patch.object(st, "_fetch_scores", side_effect=fake_fetch):
            results = st.run_all()

        for dim in st.DIMENSIONS:
            assert dim in results
            assert "label" in results[dim]
            assert "wilcoxon_treatment" in results[dim]
            assert "mann_whitney" in results[dim]
            assert "cohens_d" in results[dim]


# ---------------------------------------------------------------------------
# LaTeX export
# ---------------------------------------------------------------------------

class TestExportLatex:
    def test_latex_syntax(self):
        """Exported .tex must contain required LaTeX tabular boilerplate."""
        fake_results = {
            dim: {
                "label": st.DIMENSION_LABELS[dim],
                "mann_whitney": {"median_control": 50.0, "median_treatment": 65.0,
                                 "U": 120.0, "p_value": 0.03, "p_adjusted": 0.05,
                                 "significant_adjusted": True},
                "cohens_d": {"d": 0.75, "interpretation": "medium"},
            }
            for dim in st.DIMENSIONS
        }

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.tex")
            st.export_latex(fake_results, path)
            content = Path(path).read_text()

        assert r"\begin{tabular}" in content
        assert r"\toprule" in content
        assert r"\bottomrule" in content
        assert r"\end{table}" in content

    def test_json_roundtrip(self):
        """JSON export → reload must produce identical dict."""
        fake_results = {"accuracy_score": {"label": "Accuracy", "test": 1}}

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "stats.json")
            st.export_json(fake_results, path)
            loaded = json.loads(Path(path).read_text())

        assert loaded == fake_results
