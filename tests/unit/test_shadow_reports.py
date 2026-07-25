"""
Tests for dual (primary + shadow) report generation — RQ4 within-subject design.

The safety property under test: a shadow report must never be served to a learner.
See database/migrations/012_shadow_reports.sql.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "platform", "orchestrator"))

from app.report_service import (  # noqa: E402
    REPORT_ROLES,
    SHADOW_MODEL_LABEL,
    _is_model_generated,
)


class TestModelGeneratedDetection:
    """Shadow reports are pointless when the primary already fell back to rules."""

    @pytest.mark.parametrize("model,expected", [
        ("gemini-2.5-flash", True),
        ("gpt-4o-mini", True),
        ("gemini", True),
        ("rule-based-fallback", False),
        ("rule-based-shadow", False),
        ("", False),
        (None, False),
    ])
    def test_detection(self, model, expected):
        assert _is_model_generated({"model": model}) is expected

    def test_shadow_label_is_not_model_generated(self):
        """Guards against a shadow ever seeding another shadow."""
        assert _is_model_generated({"model": SHADOW_MODEL_LABEL}) is False

    def test_shadow_label_distinct_from_fallback(self):
        """A deliberate comparison must be distinguishable from a provider outage."""
        assert SHADOW_MODEL_LABEL != "rule-based-fallback"


class TestSaveAiReportRole:
    def _mock_conn(self):
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = [123]
        conn = MagicMock()
        conn.__enter__ = lambda s: s
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur
        return conn, cur

    def test_rejects_unknown_role(self):
        from app import report_service as rs
        with pytest.raises(ValueError):
            rs.save_ai_report("7", {"ai_report": {}}, report_role="bogus")

    @pytest.mark.parametrize("role", REPORT_ROLES)
    def test_role_is_persisted(self, role, monkeypatch):
        from app import report_service as rs
        conn, cur = self._mock_conn()
        monkeypatch.setenv("STUDY_ROUND", "2")
        with patch.object(rs, "get_db", return_value=conn):
            rs.save_ai_report("7", {"ai_report": {}, "model": "gemini"}, report_role=role)
        params = cur.execute.call_args[0][1]
        assert role in params
        assert 2 in params, "round_no must be stamped from STUDY_ROUND"

    def test_defaults_to_primary(self, monkeypatch):
        """A caller that does not think about roles must not create a shadow."""
        from app import report_service as rs
        conn, cur = self._mock_conn()
        monkeypatch.delenv("STUDY_ROUND", raising=False)
        with patch.object(rs, "get_db", return_value=conn):
            rs.save_ai_report("7", {"ai_report": {}, "model": "gemini"})
        assert "primary" in cur.execute.call_args[0][1]


class TestLearnerNeverSeesShadow:
    """The core safety property."""

    def test_latest_ai_row_filters_on_primary(self):
        from app import report_service as rs
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = None
        conn = MagicMock()
        conn.__enter__ = lambda s: s
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        with patch.object(rs, "get_db", return_value=conn):
            rs._get_latest_ai_row("7")

        sql = cur.execute.call_args[0][0]
        assert "report_role = 'primary'" in sql, (
            "the learner-facing query must exclude shadow reports; without this filter a "
            "rule-based shadow written after the primary would silently replace the "
            "treatment"
        )

    def test_every_ai_report_read_path_filters(self):
        """Fails if a new unfiltered read path is added later."""
        import pathlib
        app_dir = pathlib.Path(__file__).resolve().parents[2] / "platform" / "orchestrator" / "app"
        offenders = []
        for py in app_dir.glob("*.py"):
            text = py.read_text(encoding="utf-8")
            idx = 0
            while True:
                idx = text.find("FROM user_ai_reports", idx)
                if idx == -1:
                    break
                window = text[idx: idx + 400]
                if "report_role" not in window:
                    offenders.append(f"{py.name} @ char {idx}")
                idx += 1
        assert not offenders, f"unfiltered user_ai_reports read paths: {offenders}"
