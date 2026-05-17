"""T3.1 — DB integration tests.

Tests against the live analytics_db. Skips if DB unreachable.
"""

import uuid

import pytest

pytestmark = pytest.mark.integration


class TestDatabaseIntegration:

    def test_event_write_and_read(self, live_db):
        """Insert event → read back. Test event remains (append-only trigger blocks cleanup).
        Tests that wanted clean DBs must run after reset_for_data_collection.sh."""
        event_id = str(uuid.uuid4())
        with live_db.cursor() as cur:
            cur.execute(
                "INSERT INTO events (event_id, user_key, event_type, source) "
                "VALUES (%s, %s, %s, %s)",
                (event_id, f"test_user_{uuid.uuid4().hex[:8]}", "TEST_EVENT", "pytest"),
            )
            live_db.commit()

            cur.execute("SELECT event_type, source FROM events WHERE event_id = %s", (event_id,))
            row = cur.fetchone()
            assert row == ("TEST_EVENT", "pytest")

    def test_event_append_only_blocks_update(self, live_db):
        """Migration 008: events table must reject UPDATE."""
        with live_db.cursor() as cur:
            event_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO events (event_id, user_key, event_type, source) "
                "VALUES (%s, %s, %s, %s)",
                (event_id, "test_user", "TEST_AS_INSERT", "pytest"),
            )
            live_db.commit()

            import psycopg2
            with pytest.raises(psycopg2.errors.RaiseException, match="append-only"):
                cur.execute("UPDATE events SET event_type = 'mutated' WHERE event_id = %s", (event_id,))
            live_db.rollback()

    def test_event_append_only_blocks_delete(self, live_db):
        import psycopg2
        with live_db.cursor() as cur:
            event_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO events (event_id, user_key, event_type, source) "
                "VALUES (%s, %s, %s, %s)",
                (event_id, "test_user", "TEST_DELETE", "pytest"),
            )
            live_db.commit()
            with pytest.raises(psycopg2.errors.RaiseException, match="append-only"):
                cur.execute("DELETE FROM events WHERE event_id = %s", (event_id,))
            live_db.rollback()

    def test_experiment_assignment_unique(self, live_db):
        """Same user_id assigned twice → second insert blocked by PRIMARY KEY."""
        import psycopg2
        with live_db.cursor() as cur:
            cur.execute(
                "INSERT INTO experiment_assignment (user_id, condition, block_id, seed) "
                "VALUES (%s, %s, %s, %s)",
                (-9991, "control", 1, 42),
            )
            live_db.commit()
            with pytest.raises(psycopg2.errors.UniqueViolation):
                cur.execute(
                    "INSERT INTO experiment_assignment (user_id, condition, block_id, seed) "
                    "VALUES (%s, %s, %s, %s)",
                    (-9991, "treatment", 2, 42),
                )
            live_db.rollback()
            cur.execute("DELETE FROM experiment_assignment WHERE user_id = -9991")
            live_db.commit()

    def test_enrollment_invalid_status_rejected(self, live_db):
        """participant_enrollment.status CHECK constraint."""
        import psycopg2
        with live_db.cursor() as cur:
            with pytest.raises(psycopg2.errors.CheckViolation):
                cur.execute(
                    "INSERT INTO participant_enrollment "
                    "(participant_code, ctfd_user_id, source_group, age_range, education_level, "
                    " experience_level, irb_study_id, consent_recorded, status) "
                    "VALUES ('P_X', -1, 'kmutnb', '18-25', 'bachelor', 'beginner', 'X', now(), 'invalid_status')"
                )
            live_db.rollback()

    def test_data_collection_log_writable(self, live_db):
        with live_db.cursor() as cur:
            cur.execute(
                "INSERT INTO data_collection_log (event_type, detail) "
                "VALUES (%s, %s::jsonb) RETURNING id",
                ("test_marker", '{"test": true}'),
            )
            log_id = cur.fetchone()[0]
            live_db.commit()

            cur.execute("DELETE FROM data_collection_log WHERE id = %s", (log_id,))
            live_db.commit()
            assert log_id is not None
