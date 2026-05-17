"""T4 — REST API endpoint reliability tests.

Tests every endpoint exposed by main.py. Skips if orchestrator unreachable.
Run with:
    ORCH_BASE=http://<orchestrator>:8001 pytest tests/api
"""

import uuid

import pytest

pytestmark = pytest.mark.api


# ---------------------------------------------------------------------------
# Public / health endpoints
# ---------------------------------------------------------------------------

class TestHealthEndpoints:
    def test_health_returns_200(self, api_client):
        r = api_client.get("/health")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/json")

    def test_root_returns_200(self, api_client):
        r = api_client.get("/")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Enrollment admin endpoints
# ---------------------------------------------------------------------------

class TestEnrollmentEndpoints:
    @pytest.fixture
    def cleanup_participant(self, live_db):
        codes_created = []
        yield codes_created
        for code in codes_created:
            with live_db.cursor() as cur:
                cur.execute(
                    "SELECT ctfd_user_id FROM participant_enrollment WHERE participant_code = %s",
                    (code,),
                )
                row = cur.fetchone()
                if row:
                    ctfd_id = row[0]
                    cur.execute("DELETE FROM participant_enrollment WHERE participant_code = %s", (code,))
                    cur.execute("DELETE FROM experiment_assignment WHERE user_id = %s", (ctfd_id,))
                live_db.commit()

    def _payload(self, ctfd_id, code):
        return {
            "ctfd_user_id": ctfd_id,
            "participant_code": code,
            "source_group": "kmutnb",
            "age_range": "18-25",
            "education_level": "bachelor",
            "experience_level": "beginner",
            "consent_recorded_at": "2026-06-01T09:00:00+00:00",
            "irb_study_id": "KMUTNB-IRB-2026-T4",
        }

    def test_register_success(self, api_client, cleanup_participant):
        code = f"P_T4_{uuid.uuid4().hex[:6]}"
        ctfd_id = abs(hash(code)) % 1_000_000_000
        cleanup_participant.append(code)
        r = api_client.post("/admin/enrollment/register", json=self._payload(ctfd_id, code))
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["enrollment"]["participant_code"] == code
        assert body["enrollment"]["condition"] in ("control", "treatment")

    def test_register_duplicate_returns_400(self, api_client, cleanup_participant):
        code = f"P_T4_DUP_{uuid.uuid4().hex[:6]}"
        ctfd_id = abs(hash(code)) % 1_000_000_000
        cleanup_participant.append(code)
        # First registration succeeds
        api_client.post("/admin/enrollment/register", json=self._payload(ctfd_id, code))
        # Second registration with same user_id → 400
        r = api_client.post("/admin/enrollment/register", json=self._payload(ctfd_id, code + "_x"))
        assert r.status_code == 400
        assert "duplicate" in r.json()["detail"].lower()

    def test_register_missing_field_422(self, api_client):
        bad = {"ctfd_user_id": 1, "participant_code": "P_MISSING"}  # missing required fields
        r = api_client.post("/admin/enrollment/register", json=bad)
        assert r.status_code == 422

    def test_register_invalid_source_group_400(self, api_client):
        payload = self._payload(8888888, "P_INVALID_SRC")
        payload["source_group"] = "not_a_real_group"
        r = api_client.post("/admin/enrollment/register", json=payload)
        assert r.status_code == 400

    def test_dashboard_returns_schema(self, api_client):
        r = api_client.get("/admin/enrollment/dashboard")
        assert r.status_code == 200
        d = r.json()["dashboard"]
        assert "total_enrolled" in d
        assert "by_condition" in d
        assert "by_source" in d
        assert "by_status" in d
        assert "target_n" in d
        assert "recruitment_progress_pct" in d
        # by_condition must contain both control and treatment keys
        assert set(d["by_condition"].keys()) >= {"control", "treatment"}

    def test_withdraw_unknown_participant_404(self, api_client):
        r = api_client.post(
            "/admin/enrollment/withdraw/P_DOES_NOT_EXIST",
            json={"reason": "test", "delete_data": False},
        )
        assert r.status_code == 404

    def test_status_update_unknown_participant_404(self, api_client):
        r = api_client.post(
            "/admin/enrollment/status/P_DOES_NOT_EXIST",
            json={"status": "active"},
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Experiment summary admin endpoint
# ---------------------------------------------------------------------------

class TestExperimentAdmin:
    def test_experiment_summary_200(self, api_client):
        r = api_client.get("/admin-experiment-summary")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "summary" in body


# ---------------------------------------------------------------------------
# Report endpoints (feature gate behavior)
# ---------------------------------------------------------------------------

class TestReportEndpoints:
    def test_report_missing_user_param_422(self, api_client):
        r = api_client.get("/report")
        assert r.status_code == 422

    def test_report_unknown_user_does_not_succeed(self, api_client):
        """Unknown user must not return 2xx (no skill leak)."""
        r = api_client.get("/report?user=NONEXISTENT_USER_XYZ")
        # TODO: prefer 404, currently returns 500 (no data path raises)
        assert r.status_code >= 400, f"unknown user must error, got {r.status_code}"

    def test_get_report_unknown_user_errors(self, api_client):
        """GET /report/{user_key} for unknown user must not return 2xx."""
        r = api_client.get("/report/NONEXISTENT_USER_XYZ")
        # TODO: prefer 404, currently returns 500
        assert r.status_code >= 400, f"unknown user must error, got {r.status_code}"


# ---------------------------------------------------------------------------
# HTTP method correctness
# ---------------------------------------------------------------------------

class TestHTTPMethods:
    def test_post_only_endpoint_rejects_get(self, api_client):
        # /admin/enrollment/register is POST-only
        r = api_client.get("/admin/enrollment/register")
        assert r.status_code == 405

    def test_unknown_endpoint_404(self, api_client):
        r = api_client.get("/this/does/not/exist")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Error response hygiene
# ---------------------------------------------------------------------------

class TestErrorResponses:
    def test_validation_error_returns_json(self, api_client):
        r = api_client.post("/admin/enrollment/register", json={"bad": "input"})
        assert r.status_code == 422
        assert r.headers["content-type"].startswith("application/json")

    def test_404_returns_json(self, api_client):
        r = api_client.get("/this/does/not/exist")
        assert r.status_code == 404
        # FastAPI default 404 returns JSON
        assert r.headers["content-type"].startswith("application/json")

    def test_no_stacktrace_in_response(self, api_client):
        """Trigger a validation error and verify stack trace is not exposed."""
        r = api_client.post("/admin/enrollment/register", json={"ctfd_user_id": "not_an_int"})
        body_text = r.text.lower()
        assert "traceback" not in body_text
        assert "/home/" not in body_text  # no file system paths
