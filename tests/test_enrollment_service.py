"""Tests for enrollment_service.py and assessment_service.py.

Uses an in-memory mock DB layer (psycopg2 stubs) so tests run without a live
database.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "platform" / "orchestrator"))


# ---------------------------------------------------------------------------
# Mock DB infrastructure
# ---------------------------------------------------------------------------

class FakeDB:
    """Minimal in-memory analytics DB for testing enrollment + assessment."""

    def __init__(self):
        self.enrollment: dict[str, dict] = {}             # participant_code → row
        self.enrollment_by_ctfd: dict[int, str] = {}      # ctfd_user_id → participant_code
        self.experiment_assignment: dict[int, dict] = {}  # ctfd_user_id → assignment
        self.assessment: dict[tuple[str, str], dict] = {} # (code, type) → row
        self.collection_log: list[dict] = []

    def reset(self):
        self.__init__()


_DB = FakeDB()


def _fake_assign(user_id: int, block_size: int = 4, seed: int = 42):
    """Deterministic: even ID → control, odd → treatment, plus block tracking."""
    if user_id in _DB.experiment_assignment:
        return _DB.experiment_assignment[user_id]
    block_id = (len(_DB.experiment_assignment) // block_size) + 1
    condition = "control" if (user_id % 2 == 0) else "treatment"
    rec = {
        "user_id": user_id,
        "condition": condition,
        "block_id": block_id,
        "seed": seed,
        "assigned_at": datetime.now(tz=timezone.utc),
    }
    _DB.experiment_assignment[user_id] = rec
    return rec


# Replace DB calls in both services with operations on _DB
def _patch_enrollment(monkeypatch):
    import app.enrollment_service as es

    monkeypatch.setattr(es, "assign_participant", _fake_assign)

    def fake_log(round_no, event_type, detail):
        _DB.collection_log.append({"round_no": round_no, "event_type": event_type, "detail": detail})

    monkeypatch.setattr(es, "_log", fake_log)

    class FakeCursor:
        def __init__(self, mode="dict"):
            self.mode = mode
            self.rowcount = 0
            self._result = None

        def execute(self, sql, params=None):
            sql = " ".join(sql.split())
            params = params or ()

            if "SELECT participant_code FROM participant_enrollment WHERE participant_code = %s OR ctfd_user_id" in sql:
                code, ctfd_id = params
                if code in _DB.enrollment or ctfd_id in _DB.enrollment_by_ctfd:
                    self._result = [{"participant_code": code}]
                else:
                    self._result = []

            elif "INSERT INTO participant_enrollment" in sql:
                (code, ctfd_id, src, age, edu, exp, irb, consent, status) = params
                row = {
                    "participant_code": code, "ctfd_user_id": ctfd_id,
                    "source_group": src, "age_range": age, "education_level": edu,
                    "experience_level": exp, "irb_study_id": irb,
                    "consent_recorded": consent, "status": status,
                    "enrolled_at": datetime.now(tz=timezone.utc),
                    "withdrawn_at": None,
                }
                _DB.enrollment[code] = row
                _DB.enrollment_by_ctfd[ctfd_id] = code
                self._result = [row]
                self.rowcount = 1

            elif sql.startswith("UPDATE participant_enrollment SET status = %s WHERE participant_code"):
                status, code = params
                if code in _DB.enrollment:
                    _DB.enrollment[code]["status"] = status
                    self.rowcount = 1
                else:
                    self.rowcount = 0

            elif "UPDATE participant_enrollment SET status = %s, withdrawn_at" in sql:
                status, when, code = params
                if code in _DB.enrollment:
                    _DB.enrollment[code]["status"] = status
                    _DB.enrollment[code]["withdrawn_at"] = when
                    self.rowcount = 1
                else:
                    self.rowcount = 0

            elif "DELETE FROM participant_assessment WHERE participant_code" in sql:
                code = params[0]
                keys = [k for k in _DB.assessment if k[0] == code]
                for k in keys:
                    del _DB.assessment[k]

            elif "SELECT COUNT(*) AS n FROM participant_enrollment" in sql:
                self._result = [{"n": len(_DB.enrollment)}]

            elif "JOIN experiment_assignment" in sql:
                counts: dict[str, int] = {}
                for row in _DB.enrollment.values():
                    ea = _DB.experiment_assignment.get(row["ctfd_user_id"])
                    if ea:
                        counts[ea["condition"]] = counts.get(ea["condition"], 0) + 1
                self._result = [{"condition": c, "n": n} for c, n in counts.items()]

            elif "GROUP BY source_group" in sql:
                counts: dict[str, int] = {}
                for row in _DB.enrollment.values():
                    counts[row["source_group"]] = counts.get(row["source_group"], 0) + 1
                self._result = [{"source_group": s, "n": n} for s, n in counts.items()]

            elif "GROUP BY status" in sql:
                counts: dict[str, int] = {}
                for row in _DB.enrollment.values():
                    counts[row["status"]] = counts.get(row["status"], 0) + 1
                self._result = [{"status": s, "n": n} for s, n in counts.items()]

            elif sql.startswith("SELECT * FROM participant_enrollment WHERE participant_code"):
                code = params[0]
                row = _DB.enrollment.get(code)
                self._result = [row] if row else []

            else:
                self._result = []

        def fetchone(self):
            return self._result[0] if self._result else None

        def fetchall(self):
            return list(self._result or [])

        def __enter__(self): return self
        def __exit__(self, *a): pass

    class FakeConn:
        def cursor(self, cursor_factory=None):
            return FakeCursor()

        def __enter__(self): return self
        def __exit__(self, *a): pass

    monkeypatch.setattr(es, "_get_conn", lambda: FakeConn())


def _patch_assessment(monkeypatch):
    import app.assessment_service as asv

    def fake_log(event_type, detail):
        _DB.collection_log.append({"event_type": event_type, "detail": detail})

    monkeypatch.setattr(asv, "_log", fake_log)

    class FakeCursor:
        def __init__(self):
            self.rowcount = 0
            self._result = None

        def execute(self, sql, params=None):
            sql = " ".join(sql.split())
            params = params or ()

            if "SELECT 1 FROM participant_enrollment" in sql:
                code = params[0]
                self._result = [{"?column?": 1}] if code in _DB.enrollment else []

            elif "INSERT INTO participant_assessment" in sql:
                code, atype, score, max_score, admin_at = params
                row = {
                    "id": len(_DB.assessment) + 1,
                    "participant_code": code,
                    "assessment_type": atype,
                    "score": score, "max_score": max_score,
                    "administered_at": admin_at,
                }
                _DB.assessment[(code, atype)] = row
                self._result = [row]

            elif "SELECT * FROM participant_assessment" in sql:
                code, atype = params
                row = _DB.assessment.get((code, atype))
                self._result = [row] if row else []

            else:
                self._result = []

        def fetchone(self):
            return self._result[0] if self._result else None

        def fetchall(self):
            return list(self._result or [])

        def __enter__(self): return self
        def __exit__(self, *a): pass

    class FakeConn:
        def cursor(self, cursor_factory=None):
            return FakeCursor()

        def __enter__(self): return self
        def __exit__(self, *a): pass

    monkeypatch.setattr(asv, "_get_conn", lambda: FakeConn())


@pytest.fixture(autouse=True)
def reset_db():
    _DB.reset()
    yield


# ---------------------------------------------------------------------------
# enrollment_service tests
# ---------------------------------------------------------------------------

class TestEnrollment:
    def _enroll(self, ctfd_user_id=101, participant_code="P001"):
        from app.enrollment_service import enroll_participant
        return enroll_participant(
            ctfd_user_id=ctfd_user_id,
            participant_code=participant_code,
            source_group="kmutnb",
            age_range="18-25",
            education_level="bachelor",
            experience_level="beginner",
            consent_recorded_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            irb_study_id="KMUTNB-IRB-2026-001",
        )

    def test_enroll_assigns_group(self, monkeypatch):
        _patch_enrollment(monkeypatch)
        result = self._enroll(ctfd_user_id=101)
        assert result["participant_code"] == "P001"
        assert result["condition"] in ("control", "treatment")
        assert result["status"] == "assigned"

    def test_enroll_duplicate_rejected(self, monkeypatch):
        from app.enrollment_service import EnrollmentError
        _patch_enrollment(monkeypatch)
        self._enroll(ctfd_user_id=101, participant_code="P001")
        with pytest.raises(EnrollmentError, match="duplicate"):
            self._enroll(ctfd_user_id=101, participant_code="P002")

    def test_invalid_source_group_rejected(self, monkeypatch):
        from app.enrollment_service import EnrollmentError
        _patch_enrollment(monkeypatch)
        with pytest.raises(EnrollmentError, match="source_group"):
            from app.enrollment_service import enroll_participant
            enroll_participant(
                ctfd_user_id=999, participant_code="P999",
                source_group="invalid", age_range="18-25",
                education_level="bachelor", experience_level="beginner",
                consent_recorded_at=datetime.now(tz=timezone.utc),
                irb_study_id="X",
            )

    def test_empty_irb_id_rejected(self, monkeypatch):
        from app.enrollment_service import EnrollmentError, enroll_participant
        _patch_enrollment(monkeypatch)
        with pytest.raises(EnrollmentError, match="irb_study_id"):
            enroll_participant(
                ctfd_user_id=999, participant_code="P999",
                source_group="kmutnb", age_range="18-25",
                education_level="bachelor", experience_level="beginner",
                consent_recorded_at=datetime.now(tz=timezone.utc),
                irb_study_id="",
            )


class TestWithdrawal:
    def test_withdrawal_sets_status(self, monkeypatch):
        from app.enrollment_service import enroll_participant, record_withdrawal, get_enrollment
        _patch_enrollment(monkeypatch)
        enroll_participant(
            ctfd_user_id=101, participant_code="P001",
            source_group="kmutnb", age_range="18-25",
            education_level="bachelor", experience_level="beginner",
            consent_recorded_at=datetime.now(tz=timezone.utc),
            irb_study_id="X-1",
        )
        record_withdrawal("P001", reason="time_constraint", delete_data=False)
        row = get_enrollment("P001")
        assert row["status"] == "withdrawn"
        assert row["withdrawn_at"] is not None

    def test_withdrawal_with_data_erasure(self, monkeypatch):
        from app.enrollment_service import enroll_participant, record_withdrawal
        from app.assessment_service import record_assessment_score, get_assessment
        _patch_enrollment(monkeypatch)
        _patch_assessment(monkeypatch)
        enroll_participant(
            ctfd_user_id=101, participant_code="P001",
            source_group="kmutnb", age_range="18-25",
            education_level="bachelor", experience_level="beginner",
            consent_recorded_at=datetime.now(tz=timezone.utc),
            irb_study_id="X-1",
        )
        record_assessment_score(
            participant_code="P001", assessment_type="pretest",
            score=15, max_score=20,
            administered_at=datetime.now(tz=timezone.utc),
        )
        assert get_assessment("P001", "pretest") is not None
        record_withdrawal("P001", delete_data=True)
        assert get_assessment("P001", "pretest") is None


class TestDashboard:
    def test_counts_match_enrollments(self, monkeypatch):
        from app.enrollment_service import enroll_participant, get_study_dashboard
        _patch_enrollment(monkeypatch)
        for i, code in enumerate(["P001", "P002", "P003", "P004"], start=1):
            enroll_participant(
                ctfd_user_id=100 + i, participant_code=code,
                source_group="kmutnb", age_range="18-25",
                education_level="bachelor", experience_level="beginner",
                consent_recorded_at=datetime.now(tz=timezone.utc),
                irb_study_id="X",
            )
        d = get_study_dashboard()
        assert d["total_enrolled"] == 4
        assert d["by_condition"]["control"] + d["by_condition"]["treatment"] == 4
        assert d["target_n"] == 70


# ---------------------------------------------------------------------------
# assessment_service tests
# ---------------------------------------------------------------------------

class TestAssessment:
    def _setup(self, monkeypatch):
        from app.enrollment_service import enroll_participant
        _patch_enrollment(monkeypatch)
        _patch_assessment(monkeypatch)
        enroll_participant(
            ctfd_user_id=101, participant_code="P001",
            source_group="kmutnb", age_range="18-25",
            education_level="bachelor", experience_level="beginner",
            consent_recorded_at=datetime.now(tz=timezone.utc),
            irb_study_id="X-1",
        )

    def test_record_pretest(self, monkeypatch):
        from app.assessment_service import record_assessment_score, get_assessment
        self._setup(monkeypatch)
        record_assessment_score(
            participant_code="P001", assessment_type="pretest",
            score=14, max_score=20,
            administered_at=datetime.now(tz=timezone.utc),
        )
        a = get_assessment("P001", "pretest")
        assert a["score"] == 14
        assert a["max_score"] == 20

    def test_score_out_of_range_rejected(self, monkeypatch):
        from app.assessment_service import record_assessment_score, AssessmentError
        self._setup(monkeypatch)
        with pytest.raises(AssessmentError, match="out of range"):
            record_assessment_score(
                participant_code="P001", assessment_type="pretest",
                score=25, max_score=20,
                administered_at=datetime.now(tz=timezone.utc),
            )

    def test_assessment_without_enrollment_rejected(self, monkeypatch):
        from app.assessment_service import record_assessment_score, AssessmentError
        _patch_enrollment(monkeypatch)
        _patch_assessment(monkeypatch)
        with pytest.raises(AssessmentError, match="no enrollment record"):
            record_assessment_score(
                participant_code="P999", assessment_type="pretest",
                score=10, max_score=20,
                administered_at=datetime.now(tz=timezone.utc),
            )

    def test_learning_gain_computed(self, monkeypatch):
        from app.assessment_service import record_assessment_score, compute_learning_gain
        self._setup(monkeypatch)
        record_assessment_score(
            participant_code="P001", assessment_type="pretest",
            score=10, max_score=20,
            administered_at=datetime.now(tz=timezone.utc),
        )
        record_assessment_score(
            participant_code="P001", assessment_type="posttest",
            score=17, max_score=20,
            administered_at=datetime.now(tz=timezone.utc),
        )
        g = compute_learning_gain("P001")
        assert g["pretest_pct"] == 50.0
        assert g["posttest_pct"] == 85.0
        assert g["gain_pct"] == 35.0
