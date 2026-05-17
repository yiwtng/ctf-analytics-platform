"""T5 — End-to-end participant workflow tests.

Exercises the full lifecycle of a participant from enrollment through
withdrawal/completion, using the live orchestrator API and analytics DB.

Skips if either is unreachable. All test data is cleaned up via fixture.
"""

import uuid
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# Test participant lifecycle helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def participant_factory(api_client, live_db):
    """Create participants and clean them up after the test."""
    created: list[tuple[str, int]] = []

    def _create(source_group="kmutnb"):
        code = f"E2E_{uuid.uuid4().hex[:8]}"
        ctfd_id = abs(hash(code)) % 1_000_000_000
        payload = {
            "ctfd_user_id": ctfd_id,
            "participant_code": code,
            "source_group": source_group,
            "age_range": "26-35",
            "education_level": "master",
            "experience_level": "intermediate",
            "consent_recorded_at": "2026-06-01T09:00:00+00:00",
            "irb_study_id": "KMUTNB-IRB-2026-E2E",
        }
        r = api_client.post("/admin/enrollment/register", json=payload)
        assert r.status_code == 200, f"enrollment failed: {r.text}"
        created.append((code, ctfd_id))
        return r.json()["enrollment"], ctfd_id

    yield _create

    # Cleanup
    for code, ctfd_id in created:
        with live_db.cursor() as cur:
            cur.execute("DELETE FROM participant_assessment WHERE participant_code = %s", (code,))
            cur.execute("DELETE FROM participant_enrollment WHERE participant_code = %s", (code,))
            cur.execute("DELETE FROM experiment_assignment WHERE user_id = %s", (ctfd_id,))
            cur.execute(
                "DELETE FROM data_collection_log "
                "WHERE detail::text LIKE %s OR detail::text LIKE %s",
                (f"%{code}%", f"%{ctfd_id}%"),
            )
            live_db.commit()


# ---------------------------------------------------------------------------
# E2E flows
# ---------------------------------------------------------------------------

class TestParticipantWorkflow:

    def test_enrollment_creates_records_in_all_tables(self, participant_factory, live_db):
        """Enroll → records exist in participant_enrollment + experiment_assignment + data_collection_log."""
        enrollment, ctfd_id = participant_factory()
        code = enrollment["participant_code"]

        with live_db.cursor() as cur:
            cur.execute("SELECT status, source_group FROM participant_enrollment WHERE participant_code = %s", (code,))
            row = cur.fetchone()
            assert row[0] == "assigned"
            assert row[1] == "kmutnb"

            cur.execute("SELECT condition FROM experiment_assignment WHERE user_id = %s", (ctfd_id,))
            assert cur.fetchone()[0] in ("control", "treatment")

            cur.execute(
                "SELECT COUNT(*) FROM data_collection_log "
                "WHERE event_type = 'enrollment' AND detail::text LIKE %s",
                (f"%{code}%",),
            )
            assert cur.fetchone()[0] >= 1

    def test_pretest_posttest_recorded(self, participant_factory, api_client, live_db):
        """Record pre-test → record post-test → both retrievable + learning gain computable."""
        enrollment, _ = participant_factory()
        code = enrollment["participant_code"]

        # Pre-test
        r = api_client.post(
            f"/admin/enrollment/assessment/{code}",
            json={
                "assessment_type": "pretest",
                "score": 12.0,
                "max_score": 20.0,
                "administered_at": "2026-06-01T10:00:00+00:00",
            },
        )
        assert r.status_code == 200

        # Post-test
        r = api_client.post(
            f"/admin/enrollment/assessment/{code}",
            json={
                "assessment_type": "posttest",
                "score": 17.0,
                "max_score": 20.0,
                "administered_at": "2026-08-31T10:00:00+00:00",
            },
        )
        assert r.status_code == 200

        with live_db.cursor() as cur:
            cur.execute(
                "SELECT assessment_type, score, max_score FROM participant_assessment "
                "WHERE participant_code = %s ORDER BY assessment_type",
                (code,),
            )
            rows = cur.fetchall()
            assert len(rows) == 2
            assert rows[0] == ("posttest", 17.0, 20.0)
            assert rows[1] == ("pretest", 12.0, 20.0)

    def test_status_progression(self, participant_factory, api_client, live_db):
        """assigned → active → completed."""
        enrollment, _ = participant_factory()
        code = enrollment["participant_code"]

        for new_status in ("active", "completed"):
            r = api_client.post(
                f"/admin/enrollment/status/{code}",
                json={"status": new_status, "detail": {"note": "e2e progression"}},
            )
            assert r.status_code == 200

        with live_db.cursor() as cur:
            cur.execute("SELECT status FROM participant_enrollment WHERE participant_code = %s", (code,))
            assert cur.fetchone()[0] == "completed"

    def test_withdrawal_with_data_erasure(self, participant_factory, api_client, live_db):
        """Withdraw with delete_data=True → status=withdrawn + assessments removed."""
        enrollment, _ = participant_factory()
        code = enrollment["participant_code"]

        api_client.post(
            f"/admin/enrollment/assessment/{code}",
            json={"assessment_type": "pretest", "score": 10, "max_score": 20,
                  "administered_at": "2026-06-01T10:00:00+00:00"},
        )

        r = api_client.post(
            f"/admin/enrollment/withdraw/{code}",
            json={"reason": "time_constraint", "delete_data": True},
        )
        assert r.status_code == 200

        with live_db.cursor() as cur:
            cur.execute("SELECT status, withdrawn_at FROM participant_enrollment WHERE participant_code = %s", (code,))
            row = cur.fetchone()
            assert row[0] == "withdrawn"
            assert row[1] is not None

            cur.execute("SELECT COUNT(*) FROM participant_assessment WHERE participant_code = %s", (code,))
            assert cur.fetchone()[0] == 0

    def test_dashboard_reflects_enrollment(self, participant_factory, api_client):
        """Enroll 3 participants → dashboard total_enrolled reflects the count."""
        d_before = api_client.get("/admin/enrollment/dashboard").json()["dashboard"]
        before = d_before["total_enrolled"]

        for _ in range(3):
            participant_factory()

        d_after = api_client.get("/admin/enrollment/dashboard").json()["dashboard"]
        assert d_after["total_enrolled"] == before + 3
        total_conditions = d_after["by_condition"]["control"] + d_after["by_condition"]["treatment"]
        assert total_conditions == d_after["total_enrolled"]

    def test_block_randomization_balances_groups(self, participant_factory, api_client):
        """Enroll a full block (4) → control and treatment counts are balanced."""
        d_before = api_client.get("/admin/enrollment/dashboard").json()["dashboard"]["by_condition"]
        ctrl_before = d_before["control"]
        trt_before = d_before["treatment"]

        for _ in range(4):
            participant_factory()

        d_after = api_client.get("/admin/enrollment/dashboard").json()["dashboard"]["by_condition"]
        ctrl_delta = d_after["control"] - ctrl_before
        trt_delta = d_after["treatment"] - trt_before
        # Within one full block, the split must be exactly 2/2
        assert ctrl_delta == 2 and trt_delta == 2, \
            f"block randomization unbalanced: +{ctrl_delta} control, +{trt_delta} treatment"

    def test_duplicate_enrollment_blocked_end_to_end(self, api_client, participant_factory):
        """Re-registering same ctfd_user_id → 400."""
        enrollment, ctfd_id = participant_factory()
        payload = {
            "ctfd_user_id": ctfd_id,
            "participant_code": "P_DUP_E2E",
            "source_group": "kmutnb",
            "age_range": "18-25",
            "education_level": "bachelor",
            "experience_level": "beginner",
            "consent_recorded_at": "2026-06-01T09:00:00+00:00",
            "irb_study_id": "KMUTNB-IRB-2026-E2E",
        }
        r = api_client.post("/admin/enrollment/register", json=payload)
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Provenance gate end-to-end
# ---------------------------------------------------------------------------

class TestProvenanceGateE2E:

    def test_clean_db_passes_provenance(self, live_db):
        """After cleanup, provenance script should still pass (0 simulation users)."""
        import subprocess, sys, os
        env = os.environ.copy()
        env["ANALYTICS_DB_HOST"] = live_db.info.host
        env["ANALYTICS_DB_PORT"] = str(live_db.info.port)
        result = subprocess.run(
            [sys.executable, "tools/research/verify_data_provenance.py"],
            capture_output=True, text=True, env=env,
            cwd="/home/parallels/ctf-prod",
        )
        # 0 = clean, 1 = failed (contamination)
        assert result.returncode == 0, f"provenance check failed:\n{result.stdout}\n{result.stderr}"
        assert "PROVENANCE CHECK PASSED" in result.stdout
