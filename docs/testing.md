# Testing Strategy

This document describes the 5-level test architecture used to validate
the CTF Analytics Platform. Each level serves a distinct purpose and is
isolated so that a failure can be localized to a specific concern.

The total test count (as of this writing) is **132 tests** across all
levels. The unit and PII-leak tests run in CI on every push; integration,
API, and E2E tests run when a live environment is available.

---

## 1. Test Levels

| Level | Purpose | Scope | Requires | Marker |
|-------|---------|-------|----------|--------|
| **T1 Smoke** | Service availability | Health endpoints, DB connectivity, schema | Live services | `smoke` |
| **T2 Unit** | Correctness of analytics computation | 7-dim formulas, statistics, enrollment logic | Nothing | `unit` |
| **T3 Integration** | Component communication + PII compliance | DB ↔ orchestrator, LLM prompt structure | Live DB | `integration` |
| **T4 API** | Endpoint reliability | All REST endpoints | Live orchestrator + DB | `api` |
| **T5 E2E** | Complete user workflow | Enroll → assess → progress → withdraw | Live orchestrator + DB | `e2e` |

---

## 2. Running Tests

### Local — unit only (no infrastructure needed)
```bash
pip install -r requirements-pinned.txt -r requirements-dev.txt
pytest tests/unit -v
```

### Local — with live services
```bash
# Ensure docker compose is running first
ORCH_BASE=http://172.18.0.5:8001 \
ANALYTICS_DB_HOST=localhost ANALYTICS_DB_PORT=5433 \
pytest tests/ -v
```

### By marker
```bash
pytest -m unit          # pure logic only
pytest -m smoke         # availability checks
pytest -m integration   # DB-dependent
pytest -m api           # endpoint-dependent
pytest -m e2e           # full workflow
```

### Coverage report (unit tests only)
```bash
pytest tests/unit --cov=platform/orchestrator/app --cov=tools --cov-report=term
```

---

## 3. Test Inventory

### T1 Smoke (6 tests)
File: `tests/smoke/test_smoke.py`
- Orchestrator `/health`, `/`
- Analytics DB connection
- All 10 required research tables present
- Append-only trigger active on `events` (migration 008)
- `data_collection_log` initialized

### T2 Unit (84 tests)
- `tests/unit/test_skill_scoring.py` (29) — all 7-dim formulas verified against hand-calculated values, clamp behavior, level boundaries
- `tests/unit/test_experiment.py` (13) — block randomization, deterministic seed, fail-safe `is_treatment`
- `tests/unit/test_validation_service.py` (10) — ICC, Cronbach's α, convergent validity, EFA graceful skip
- `tests/unit/test_feedback_quality.py` (9) — Likert constraints, Cohen's κ, idempotent storage
- `tests/unit/test_statistical_tests.py` (12) — Wilcoxon, Mann-Whitney U, Cohen's d, Holm-Bonferroni, LaTeX export
- `tests/unit/test_enrollment_logic.py` (11) — enrollment, withdrawal (incl. PDPA erasure), dashboard, assessment scoring

### T3 Integration (16 tests)
- `tests/integration/test_db_integration.py` (6) — append-only trigger blocks UPDATE/DELETE, PK/CHECK constraints
- `tests/integration/test_llm_pipeline.py` (10) — **PII leak test** verifies prompt contains only pseudonym + aggregated stats (no email/IP/phone/national ID/name), prompt structure, feature gate fail-safe

### T4 API (18 tests)
File: `tests/api/test_api_endpoints.py` — all `/admin/enrollment/*` endpoints, `/health`, `/report`, `/admin-experiment-summary`, HTTP method correctness, error response hygiene (no stack trace leak)

### T5 E2E (8 tests)
File: `tests/e2e/test_participant_workflow.py` — full enrollment lifecycle, pre/post-test recording, status progression, withdrawal with data erasure, block randomization balance, duplicate prevention, provenance gate pass

---

## 4. Critical Tests for IRB / Reviewer Evidence

Two test areas serve as compliance evidence for the IEEE TLT manuscript
and the KMUTNB IRB submission:

### PDPA Compliance — `test_llm_pipeline.py::TestPromptPII`
Verifies that the prompt sent to Google Gemini and OpenAI contains:
- **Allowed:** Pseudonymous participant code (P001), aggregated event counts, computed skill scores
- **Forbidden:** Email addresses, IPv4 addresses, Thai phone numbers, national IDs, real Thai name prefixes, raw ISO 8601 timestamps

An injection sub-test confirms the PII detector itself works by deliberately
inserting an email and asserting it gets flagged.

### Research Integrity — `verify_data_provenance` gate
Both `statistical_tests.py` and `export_anonymized_dataset.py` refuse to run
if the DB contains any user not present in `participant_enrollment`. The
E2E test `test_clean_db_passes_provenance` confirms the gate works end-to-end.

---

## 5. Determinism

All unit tests use fixed seeds (experiment: seed=42, statistical tests:
fixed-seed `np.random.default_rng(42)`). Integration and E2E tests use
unique random participant codes per run to prevent collisions but never
introduce non-determinism in assertion paths.

If a test passes once but fails on rerun without code changes, that's a
bug — file an issue. The 60-second pytest timeout catches hangs.

---

## 6. Continuous Integration

`.github/workflows/test.yml` runs the unit suite (and coverage report)
on every push and pull request. The integration/API/E2E tiers require a
live docker compose stack and are intended for local pre-merge runs.

`.github/workflows/security.yml` runs gitleaks on every push to catch
accidentally committed secrets.

---

## 7. What Tests Don't Cover

These are explicit non-goals for this test suite:

- **CTFd internal logic** — CTFd is treated as a black box (per project
  rule: never modify CTFd core). Integration with CTFd is verified at
  the webhook/API boundary only.
- **Browser UI** — there are no Playwright/Selenium tests; UI is
  exercised manually before each round and validated by participants.
- **Load / performance** — out of scope for a small-cohort longitudinal
  study (n ≈ 70).
- **Live LLM calls** — Gemini API is mocked in tests. Calling the live
  API is exercised manually before each data collection round.
