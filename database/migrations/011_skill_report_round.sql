-- Migration 011: Give each skill report the study round it belongs to.
--
-- BLOCKING DEFECT this fixes (verified against the live database 2026-07-25):
--
--   tools/analysis/statistical_tests.py runs
--       SELECT r.user_key, r.accuracy_score, ..., e.condition, e.round_no
--       FROM user_skill_reports r
--       LEFT JOIN experiment_assignment e ON r.user_key = CAST(e.user_id AS TEXT)
--   which fails with:
--       ERROR: column e.round_no does not exist
--
--   experiment_assignment is (user_id, condition, block_id, seed, assigned_at)
--   user_skill_reports  has no round column either.
--
-- So there is currently NO way to say which of the three rounds a skill report
-- belongs to. That blocks H1 entirely: wilcoxon_within() compares round 1 against
-- round 3, and _fetch_scores(round_no=...) cannot filter at all. Since H1 (does
-- the feedback improve skill development?) is the study's primary research
-- question, this must be fixed before any participant is enrolled — the round of
-- a report cannot be reconstructed reliably after the fact.
--
-- The round belongs on the report, not on the assignment: assignment is one row
-- per participant for the whole study, while a participant produces one report
-- per round.

-- SECOND BLOCKING DEFECT in the same table (verified 2026-07-25): report_service
-- save_skill_report() also writes overall_level and summary_json, neither of
-- which exists in the live table:
--     ERROR: column "overall_level" of relation "user_skill_reports" does not exist
-- So no skill report could be persisted at all — the core of the pipeline. Both
-- columns are added here. (user_ai_reports was checked and is fine.)

ALTER TABLE user_skill_reports
    ADD COLUMN IF NOT EXISTS round_no      INTEGER,
    ADD COLUMN IF NOT EXISTS overall_level TEXT,
    ADD COLUMN IF NOT EXISTS summary_json  JSONB;

COMMENT ON COLUMN user_skill_reports.round_no IS
    'Study round (1..3) this report summarises; set from STUDY_ROUND at generation time';
COMMENT ON COLUMN user_skill_reports.overall_level IS
    'Developing (<60) | Intermediate (60-79) | Advanced (>=80), derived from the mean of the seven dimensions';
COMMENT ON COLUMN user_skill_reports.summary_json IS
    'Raw stats + scores snapshot backing this report, for traceability';

-- Existing rows predate the round-aware pipeline. The table is empty in
-- production (verified: 0 rows), so this backfill is a no-op there; it exists so
-- the migration is safe on development databases that do hold rows.
UPDATE user_skill_reports SET round_no = 1 WHERE round_no IS NULL;

ALTER TABLE user_skill_reports
    DROP CONSTRAINT IF EXISTS user_skill_reports_round_no_check;
ALTER TABLE user_skill_reports
    ADD CONSTRAINT user_skill_reports_round_no_check
    CHECK (round_no IS NULL OR round_no BETWEEN 1 AND 3);

-- Deliberately left nullable: a report generated outside a study round (ad-hoc
-- admin regeneration) should be storable and then excluded from analysis, rather
-- than silently mislabelled as belonging to a round.

CREATE INDEX IF NOT EXISTS idx_user_skill_reports_round
ON user_skill_reports(round_no);

CREATE INDEX IF NOT EXISTS idx_user_skill_reports_user_round
ON user_skill_reports(user_key, round_no);
