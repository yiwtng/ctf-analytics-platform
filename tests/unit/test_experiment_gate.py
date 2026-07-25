"""
The condition gate: AI feedback is the intervention and must reach the treatment
group only.

Regression cover for a defect that would have voided the primary research
question. The gate read `user_id is None or is_treatment(user_id)`, and neither
call site passed user_id, so it always short-circuited to True: every control
participant received the LLM report. Nothing looked wrong from outside -- reports
generated normally and the response labelled the user "treatment".
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "platform", "orchestrator"))

from app.report_service import _user_id_from_key  # noqa: E402


class TestUserIdFromKey:
    @pytest.mark.parametrize("key,expected", [
        ("7", 7), ("42", 42), (" 9002 ", 9002), (7, 7),
    ])
    def test_numeric_keys_resolve(self, key, expected):
        """Participant keys are the CTFd user id as text; the analysis joins on that."""
        assert _user_id_from_key(key) == expected

    @pytest.mark.parametrize("key", ["pilot01", "", "  ", "admin", None, "7a"])
    def test_non_numeric_keys_do_not_resolve(self, key):
        assert _user_id_from_key(key) is None


class TestGate:
    """Exercises the decision only, with the surrounding I/O stubbed out."""

    def _run(self, user_key, *, assigned_treatment=None, allow_unassigned=False):
        from app import report_service as rs

        calls = {"ai": False}

        def fake_analyze(user_key, stats, scores):
            calls["ai"] = True
            return {"model": "gemini-2.5-flash", "ai_report": {}, "raw_response": {}}

        def fake_is_treatment(uid):
            if assigned_treatment is None:
                raise AssertionError("is_treatment called for an unassigned key")
            return assigned_treatment

        import app.experiment as experiment

        with patch.object(rs, "aggregate_user_stats", return_value={}), \
             patch.object(rs, "derive_scores", return_value={}), \
             patch.object(rs, "save_skill_report", return_value=1), \
             patch.object(rs, "_get_cached_ai_result", return_value=None), \
             patch.object(rs, "save_ai_report", return_value=2), \
             patch.object(rs, "analyze_user_with_gemini", side_effect=fake_analyze), \
             patch.object(experiment, "is_treatment", side_effect=fake_is_treatment):
            result = rs.generate_user_report(user_key, allow_unassigned_ai=allow_unassigned)
        return result, calls["ai"]

    def test_control_gets_no_ai_report(self):
        """The defect this file exists for."""
        result, ai_called = self._run("9002", assigned_treatment=False)
        assert ai_called is False, "control participant received AI feedback"
        assert result["ai_report_id"] is None
        assert result["condition"] == "control"

    def test_treatment_gets_ai_report(self):
        result, ai_called = self._run("9001", assigned_treatment=True)
        assert ai_called is True
        assert result["condition"] == "treatment"

    def test_unassigned_key_defaults_to_no_ai(self):
        """Failing closed: an unresolvable key must not be treated as treatment."""
        result, ai_called = self._run("pilot01")
        assert ai_called is False
        assert result["ai_report_id"] is None
        assert result["condition"] == "unassigned"

    def test_unassigned_key_can_be_opted_in(self):
        """Administrative regeneration stays possible, but only explicitly."""
        result, ai_called = self._run("pilot01", allow_unassigned=True)
        assert ai_called is True

    def test_opt_in_never_overrides_control(self):
        """allow_unassigned_ai must not become a way to leak into the control group."""
        result, ai_called = self._run("9002", assigned_treatment=False, allow_unassigned=True)
        assert ai_called is False, "explicit control assignment was overridden"
        assert result["condition"] == "control"
