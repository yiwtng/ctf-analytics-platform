-- Migration 012: Distinguish the report shown to the learner from the shadow
-- report generated only for blind expert comparison, and record which round each
-- report belongs to.
--
-- WHY THIS EXISTS
-- RQ4 asks whether LLM-generated feedback is rated better than the deterministic
-- rule-based generator. The pre-registered design is within-subject: for the same
-- participant-round, the same underlying skill data is rendered twice — once by the
-- LLM, once by the rule-based generator — and experts rate both blind. That requires
-- storing two reports per participant-round.
--
-- THE HAZARD THIS COLUMN PREVENTS
-- Three code paths fetch a learner's report with
--     SELECT ... FROM user_ai_reports WHERE user_key = ? ORDER BY generated_at DESC LIMIT 1
-- With two reports per round and no role marker, the shadow (rule-based) report would
-- be served to the learner whenever it was written last. The treatment group would
-- silently receive rule-based feedback instead of LLM feedback — destroying the
-- intervention while leaving no trace in the data. report_role makes the learner-facing
-- report explicit, and every read path filters on it.
--
-- round_no is added for the same reason as migration 011: expert feedback ratings are
-- keyed by (rater, participant, round, source), so a report must know its round to be
-- paired with its rating.

ALTER TABLE user_ai_reports
    ADD COLUMN IF NOT EXISTS report_role VARCHAR(16),
    ADD COLUMN IF NOT EXISTS round_no    INTEGER;

COMMENT ON COLUMN user_ai_reports.report_role IS
    'primary = shown to the learner (the intervention); shadow = generated only for blind expert rating, never displayed';
COMMENT ON COLUMN user_ai_reports.round_no IS
    'Study round (1..3) this report belongs to; set from STUDY_ROUND at generation time';

-- Existing rows predate shadow generation and were all learner-facing.
UPDATE user_ai_reports SET report_role = 'primary' WHERE report_role IS NULL;

ALTER TABLE user_ai_reports ALTER COLUMN report_role SET NOT NULL;

ALTER TABLE user_ai_reports
    DROP CONSTRAINT IF EXISTS user_ai_reports_report_role_check;
ALTER TABLE user_ai_reports
    ADD CONSTRAINT user_ai_reports_report_role_check
    CHECK (report_role IN ('primary', 'shadow'));

ALTER TABLE user_ai_reports
    DROP CONSTRAINT IF EXISTS user_ai_reports_round_no_check;
ALTER TABLE user_ai_reports
    ADD CONSTRAINT user_ai_reports_round_no_check
    CHECK (round_no IS NULL OR round_no BETWEEN 1 AND 3);

-- Read paths filter on report_role and order within a user; index accordingly.
CREATE INDEX IF NOT EXISTS idx_user_ai_reports_user_role
ON user_ai_reports(user_key, report_role, generated_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_ai_reports_round
ON user_ai_reports(round_no);
