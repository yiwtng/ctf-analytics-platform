"""T1 — Smoke tests for service availability.

These tests skip if services are not running. They verify the platform is
ready to accept traffic, not that any specific behavior is correct.

Run with:
    pytest tests/smoke -m smoke
"""

import pytest

REQUIRED_TABLES = {
    "events",
    "user_skill_reports",
    "user_ai_reports",
    "participant_feedback",
    "experiment_assignment",
    "participant_enrollment",
    "participant_assessment",
    "expert_rating",
    "feedback_rating",
    "data_collection_log",
}


@pytest.mark.smoke
class TestServiceAvailability:

    def test_orchestrator_health(self, api_client):
        r = api_client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True or body.get("status") in ("ok", "healthy")

    def test_orchestrator_root(self, api_client):
        r = api_client.get("/")
        assert r.status_code == 200

    def test_database_connection(self, live_db):
        with live_db.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone()[0] == 1

    def test_required_tables_exist(self, live_db):
        with live_db.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
            present = {r[0] for r in cur.fetchall()}
        missing = REQUIRED_TABLES - present
        assert not missing, f"Missing tables: {missing}"

    def test_append_only_trigger_active(self, live_db):
        """Migration 008: events trigger must be present and prevent mutation."""
        with live_db.cursor() as cur:
            cur.execute(
                "SELECT trigger_name FROM information_schema.triggers "
                "WHERE event_object_table = 'events'"
            )
            triggers = {r[0] for r in cur.fetchall()}
        assert "no_event_update" in triggers, f"append-only trigger missing: {triggers}"

    def test_data_collection_log_initialized(self, live_db):
        """After reset, data_collection_log should have at least one entry."""
        with live_db.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM data_collection_log")
            count = cur.fetchone()[0]
        assert count >= 1, "data_collection_log is empty — did reset_for_data_collection.sh run?"
