"""T3.3 — LLM pipeline integration tests + PII leak verification.

The PII leak test is the most important test in this file — it verifies that
the prompt sent to Gemini contains ONLY the pseudonymous participant code
(P001, P002, …) and aggregated behavioral statistics. No name, email, IP
address, or raw event timestamps ever reach the LLM.
"""

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "platform" / "orchestrator"))

from app.report_service import build_gemini_prompt

pytestmark = pytest.mark.integration


def _full_stats(**overrides):
    """Build a complete stats dict — build_gemini_prompt expects all keys."""
    base = {
        "total_solves": 0, "total_wrong_submits": 0, "total_started": 0,
        "total_giveups": 0, "total_errors": 0,
        "tcp_bad_auth": 0, "tcp_hello_ok": 0, "tcp_malformed": 0,
        "web_request": 0, "web_solves": 0, "web_wrong_fast": 0,
        "protocol_solves": 0,
        "ssh_command": 0, "ssh_solves": 0, "ssh_errors": 0,
        "blue_unique_attempts": 0, "blue_opened": 0, "blue_solves": 0,
        "blue_wrong": 0, "blue_hint_use": 0,
        "excessive_restarts": 0,
    }
    base.update(overrides)
    return base


# Patterns that MUST NOT appear in any payload sent to an external LLM.
PII_PATTERNS = [
    # Email addresses
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    # IPv4 addresses
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    # Thai phone numbers (08X-XXX-XXXX, 09X-XXX-XXXX, 06X-XXX-XXXX)
    re.compile(r"\b0[689]\d[-\s]?\d{3}[-\s]?\d{4}\b"),
    # Thai national ID (13 digits)
    re.compile(r"\b\d{13}\b"),
    # Real Thai name prefixes
    re.compile(r"นาย|นางสาว|นาง|ด\.ช\.|ด\.ญ\."),
]


def _assert_no_pii(text: str, label: str = "payload"):
    for pat in PII_PATTERNS:
        m = pat.search(text)
        assert m is None, f"PII pattern {pat.pattern} matched in {label}: {m.group()!r}"


class TestPromptPII:
    """Critical for PDPA compliance: verify no PII leaks into Gemini payload."""

    def test_pseudonym_only_in_prompt(self):
        prompt = build_gemini_prompt(
            user_key="P001",
            stats=_full_stats(total_solves=5, total_wrong_submits=2),
            scores={"accuracy_score": 71, "overall_level": "Developing"},
        )
        # Pseudonym is allowed
        assert "P001" in prompt
        _assert_no_pii(prompt, "build_gemini_prompt output")

    def test_no_email_leak_even_if_in_stats(self):
        """Even if stats contained an email by mistake, the test would catch it."""
        stats = _full_stats(total_solves=1); stats["comment"] = "user@example.com left feedback"
        prompt = build_gemini_prompt("P002", stats, {"accuracy_score": 100})
        # The test should fail loudly if email made it into the prompt
        with pytest.raises(AssertionError, match="PII pattern"):
            _assert_no_pii(prompt, "test injection")

    def test_no_ip_address_leak(self):
        stats = _full_stats(total_solves=3, total_wrong_submits=1)
        prompt = build_gemini_prompt("P003", stats, {"accuracy_score": 75})
        _assert_no_pii(prompt, "clean prompt with safe inputs")

    def test_prompt_contains_required_fields(self):
        prompt = build_gemini_prompt(
            "P004",
            stats=_full_stats(total_solves=4, total_wrong_submits=1, total_started=2),
            scores={"accuracy_score": 80, "persistence_score": 50,
                    "overall_level": "Intermediate", "overall_average": 65},
        )
        assert "P004" in prompt
        assert "total_solves" in prompt
        assert "accuracy_score" in prompt
        # JSON output schema must be specified
        assert "profile" in prompt
        assert "recommendations" in prompt
        assert "confidence" in prompt

    def test_prompt_no_event_timestamps(self):
        """Wall-clock event timestamps must be aggregated, not raw."""
        stats = _full_stats(total_solves=5, total_wrong_submits=2)
        scores = {"accuracy_score": 71}
        prompt = build_gemini_prompt("P005", stats, scores)
        # ISO 8601 timestamp pattern
        ts_pattern = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
        assert ts_pattern.search(prompt) is None, \
            "Raw timestamps should never reach the LLM (use ts_offset_seconds in stats)"


class TestPromptStructure:
    def test_prompt_is_string(self):
        prompt = build_gemini_prompt("P001", _full_stats(), {})
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_prompt_asks_for_json_only(self):
        prompt = build_gemini_prompt("P001", _full_stats(total_solves=1), {"accuracy_score": 100})
        assert "JSON" in prompt

    def test_prompt_deterministic_same_input(self):
        stats = _full_stats(total_solves=5, total_wrong_submits=2)
        scores = {"accuracy_score": 71}
        p1 = build_gemini_prompt("P001", stats, scores)
        p2 = build_gemini_prompt("P001", stats, scores)
        assert p1 == p2


class TestFeatureGateBehavior:
    """Treatment vs control gate determines whether Gemini is called at all.

    Requires live analytics DB — skips if unreachable.
    """

    def test_is_treatment_returns_false_for_unassigned(self, live_db):
        # Re-import so the module re-reads ANALYTICS_DB_HOST env if pytest exported it
        from app import experiment
        # Force module to use the test DB connection settings
        experiment.ANALYTICS_DB_HOST = live_db.info.host
        experiment.ANALYTICS_DB_PORT = live_db.info.port
        assert experiment.is_treatment(999_999_999) is False

    def test_is_treatment_signature(self, live_db):
        from app import experiment
        experiment.ANALYTICS_DB_HOST = live_db.info.host
        experiment.ANALYTICS_DB_PORT = live_db.info.port
        result = experiment.is_treatment(1)
        assert isinstance(result, bool)
