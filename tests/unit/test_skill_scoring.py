"""T2.1 — Unit tests for 7-dimension skill scoring formulas.

Each formula in report_service.derive_scores() is verified against a
hand-calculated reference value. All scores must be clamped to [0, 100].
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "platform" / "orchestrator"))

from app.report_service import derive_scores, clamp_score


def _make_stats(**overrides):
    """Build a stats dict with sensible defaults that can be overridden per test."""
    base = {
        "total_solves": 0, "total_wrong_submits": 0, "total_started": 0,
        "total_giveups": 0, "total_errors": 0,
        "web_request": 0, "web_solves": 0, "web_wrong_fast": 0,
        "tcp_hello_ok": 0, "tcp_malformed": 0, "tcp_bad_auth": 0, "protocol_solves": 0,
        "ssh_command": 0, "ssh_solves": 0, "ssh_errors": 0,
        "blue_unique_attempts": 0, "blue_opened": 0, "blue_solves": 0,
        "blue_wrong": 0, "blue_hint_use": 0,
        "excessive_restarts": 0,
    }
    base.update(overrides)
    return base


@pytest.mark.unit
class TestClampScore:
    def test_clamp_negative(self):
        assert clamp_score(-10) == 0

    def test_clamp_zero(self):
        assert clamp_score(0) == 0

    def test_clamp_mid(self):
        assert clamp_score(55) == 55

    def test_clamp_max(self):
        assert clamp_score(100) == 100

    def test_clamp_above_max(self):
        assert clamp_score(150) == 100


@pytest.mark.unit
class TestAccuracy:
    def test_accuracy_basic(self):
        # 8 / (8 + 2) = 0.8 → 80
        s = _make_stats(total_solves=8, total_wrong_submits=2)
        assert derive_scores(s)["accuracy_score"] == 80

    def test_accuracy_perfect(self):
        s = _make_stats(total_solves=10, total_wrong_submits=0)
        assert derive_scores(s)["accuracy_score"] == 100

    def test_accuracy_zero_attempts(self):
        # No submissions → spec returns 100 (baseline), not ZeroDivisionError
        s = _make_stats(total_solves=0, total_wrong_submits=0)
        assert derive_scores(s)["accuracy_score"] == 100

    def test_accuracy_all_wrong(self):
        s = _make_stats(total_solves=0, total_wrong_submits=5)
        assert derive_scores(s)["accuracy_score"] == 0


@pytest.mark.unit
class TestPersistence:
    def test_persistence_formula_positive(self):
        # 40 + started*5 - giveups*10 - errors*3
        # 40 + 3*5 - 0*10 - 1*3 = 52
        s = _make_stats(total_started=3, total_giveups=0, total_errors=1)
        assert derive_scores(s)["persistence_score"] == 52

    def test_persistence_clamped_zero(self):
        # 40 + 0 - 5*10 = -10 → clamp 0
        s = _make_stats(total_giveups=5)
        assert derive_scores(s)["persistence_score"] == 0

    def test_persistence_clamped_max(self):
        # 40 + 20*5 = 140 → clamp 100
        s = _make_stats(total_started=20)
        assert derive_scores(s)["persistence_score"] == 100


@pytest.mark.unit
class TestWebRecon:
    def test_web_recon_formula(self):
        # 50 + 8*2 - 0*8 + 1*15 = 50 + 16 + 15 = 81
        s = _make_stats(web_request=8, web_solves=1, web_wrong_fast=0)
        assert derive_scores(s)["web_recon_score"] == 81

    def test_web_recon_penalty(self):
        # 50 + 0 - 5*8 + 0 = 10
        s = _make_stats(web_wrong_fast=5)
        assert derive_scores(s)["web_recon_score"] == 10


@pytest.mark.unit
class TestProtocol:
    def test_protocol_formula(self):
        # 50 + 2*10 + 1*20 - 0*6 - 1*5 = 85
        s = _make_stats(tcp_hello_ok=2, protocol_solves=1, tcp_bad_auth=1)
        assert derive_scores(s)["protocol_score"] == 85

    def test_protocol_heavy_penalty(self):
        # 50 + 0 + 0 - 10*6 - 5*5 = 50 - 85 = -35 → clamp 0
        s = _make_stats(tcp_malformed=10, tcp_bad_auth=5)
        assert derive_scores(s)["protocol_score"] == 0


@pytest.mark.unit
class TestSshPivot:
    def test_ssh_pivot_formula(self):
        # 50 + 5*3 + 1*20 - 0 = 85
        s = _make_stats(ssh_command=5, ssh_solves=1)
        assert derive_scores(s)["ssh_pivot_score"] == 85

    def test_ssh_pivot_penalty(self):
        # 50 + 0 + 0 - 10*8 = -30 → 0
        s = _make_stats(ssh_errors=10)
        assert derive_scores(s)["ssh_pivot_score"] == 0


@pytest.mark.unit
class TestBlueAnalysis:
    def test_blue_analysis_formula(self):
        # 50 + 3*4 + min(5,10) + 2*12 - 1*4 - 1*3 = 50+12+5+24-4-3 = 84
        s = _make_stats(blue_unique_attempts=3, blue_opened=5,
                        blue_solves=2, blue_wrong=1, blue_hint_use=1)
        assert derive_scores(s)["blue_analysis_score"] == 84

    def test_blue_opened_capped_at_10(self):
        # blue_opened=20 should add only min(20,10)=10
        # 50 + 0 + 10 + 0 - 0 - 0 = 60
        s = _make_stats(blue_opened=20)
        assert derive_scores(s)["blue_analysis_score"] == 60


@pytest.mark.unit
class TestTimeEfficiency:
    def test_time_efficiency_baseline(self):
        # 70 - 0 - 0 - 0 = 70
        s = _make_stats()
        assert derive_scores(s)["time_efficiency_score"] == 70

    def test_time_efficiency_penalty(self):
        # 70 - 2*10 - 3*3 - 1*3 = 70-20-9-3 = 38
        s = _make_stats(excessive_restarts=2, total_wrong_submits=3, total_errors=1)
        assert derive_scores(s)["time_efficiency_score"] == 38

    def test_time_efficiency_floor(self):
        s = _make_stats(excessive_restarts=20)
        assert derive_scores(s)["time_efficiency_score"] == 0


@pytest.mark.unit
class TestOverall:
    def test_overall_is_mean_of_seven(self):
        s = _make_stats(total_solves=8, total_wrong_submits=2,
                        total_started=3, total_errors=1)
        result = derive_scores(s)
        dims = ["web_recon_score", "protocol_score", "ssh_pivot_score",
                "blue_analysis_score", "persistence_score", "accuracy_score",
                "time_efficiency_score"]
        expected_avg = sum(result[d] for d in dims) // 7
        assert result["overall_average"] == expected_avg

    def test_level_advanced(self):
        # All max scores → level=Advanced
        s = _make_stats(total_solves=100, total_started=20,
                        web_request=50, web_solves=10,
                        tcp_hello_ok=10, protocol_solves=5,
                        ssh_command=20, ssh_solves=5,
                        blue_unique_attempts=20, blue_opened=20, blue_solves=10)
        assert derive_scores(s)["overall_level"] == "Advanced"

    def test_level_developing(self):
        # All zero → developing baseline
        s = _make_stats()
        result = derive_scores(s)
        assert result["overall_level"] in ("Developing", "Intermediate")


@pytest.mark.unit
class TestBounded:
    def test_all_dimensions_in_range(self, sample_stats):
        result = derive_scores(sample_stats)
        dims = ["web_recon_score", "protocol_score", "ssh_pivot_score",
                "blue_analysis_score", "persistence_score", "accuracy_score",
                "time_efficiency_score"]
        for d in dims:
            assert 0 <= result[d] <= 100, f"{d}={result[d]} out of [0,100]"

    def test_deterministic(self, sample_stats):
        r1 = derive_scores(sample_stats.copy())
        r2 = derive_scores(sample_stats.copy())
        r3 = derive_scores(sample_stats.copy())
        assert r1 == r2 == r3

    def test_empty_events_no_crash(self):
        s = _make_stats()
        result = derive_scores(s)
        assert result is not None
        for v in result.values():
            if isinstance(v, (int, float)):
                assert not (v != v)  # NaN check
