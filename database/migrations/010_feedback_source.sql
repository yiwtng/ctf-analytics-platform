-- Migration 010: Align feedback_rating with the code, and record which
-- generator produced the feedback being rated.
--
-- IMPORTANT — this migration is written against the schema that actually exists
-- in production, which was created by database/scripts/reset_analytics_db.sql,
-- NOT by migration 007. Because 007 uses CREATE TABLE IF NOT EXISTS and the
-- reset script had already created the table, 007 silently no-opped. The live
-- table therefore differs from 007:
--
--   live:  id, rater_id, participant_code, round_no,
--          relevance, specificity, actionability, accuracy, rated_at
--   007:   ... relevance, actionability, accuracy, comment, created_at
--          + UNIQUE (rater_id, participant_code, round_no)
--
-- Consequences verified against the live database on 2026-07-25:
--   1. store_feedback_rating() INSERTs "comment"  -> ERROR: column does not exist
--   2. "specificity" is NOT NULL with no default   -> INSERT would fail anyway
--   3. there is NO unique constraint on the table  -> the ON CONFLICT clause
--      would fail with "no unique or exclusion constraint matching"
--
-- This migration keeps the 4-dimension rubric (specificity is retained: Shute
-- (2008) treats specificity as distinct from actionability) and makes the table
-- satisfy the code rather than dropping a column that already exists.

-- 1. Columns the code writes but the live table lacks.
ALTER TABLE feedback_rating
    ADD COLUMN IF NOT EXISTS comment         TEXT,
    ADD COLUMN IF NOT EXISTS feedback_source VARCHAR(16),
    ADD COLUMN IF NOT EXISTS model_name      VARCHAR(64);

COMMENT ON COLUMN feedback_rating.feedback_source IS
    'Generator tier that produced the rated feedback: gemini | openai | rule_based | unknown';
COMMENT ON COLUMN feedback_rating.model_name IS
    'Exact model identifier (e.g. gemini-2.5-flash, gpt-4o-mini); NULL for rule_based';

-- 2. Backfill and constrain the source. Only development data should exist here;
--    reset_for_data_collection.sh wipes the table before the real study.
UPDATE feedback_rating SET feedback_source = 'unknown' WHERE feedback_source IS NULL;
ALTER TABLE feedback_rating ALTER COLUMN feedback_source SET NOT NULL;

ALTER TABLE feedback_rating
    DROP CONSTRAINT IF EXISTS feedback_rating_feedback_source_check;
ALTER TABLE feedback_rating
    ADD CONSTRAINT feedback_rating_feedback_source_check
    CHECK (feedback_source IN ('gemini', 'openai', 'rule_based', 'unknown'));

-- 3. The uniqueness key the ON CONFLICT clause requires. Including the source
--    lets one participant-round be rated once per generator, which supports the
--    stronger within-subject design (the same learner's performance rendered as
--    both LLM and rule-based feedback, rated blind).
--
--    Any pre-existing unique key on (rater_id, participant_code, round_no) is
--    dropped by shape rather than by name, since production and 007 may have
--    named it differently — or not created it at all.
DO $$
DECLARE
    con_name TEXT;
BEGIN
    SELECT c.conname INTO con_name
    FROM pg_constraint c
    WHERE c.conrelid = 'feedback_rating'::regclass
      AND c.contype = 'u'
      AND (
        SELECT array_agg(a.attname ORDER BY a.attname)
        FROM unnest(c.conkey) AS k(attnum)
        JOIN pg_attribute a
          ON a.attrelid = c.conrelid AND a.attnum = k.attnum
      ) = ARRAY['participant_code', 'rater_id', 'round_no']::name[]
    LIMIT 1;

    IF con_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE feedback_rating DROP CONSTRAINT %I', con_name);
    END IF;
END $$;

ALTER TABLE feedback_rating
    DROP CONSTRAINT IF EXISTS feedback_rating_rater_participant_round_source_key;
ALTER TABLE feedback_rating
    ADD CONSTRAINT feedback_rating_rater_participant_round_source_key
    UNIQUE (rater_id, participant_code, round_no, feedback_source);

CREATE INDEX IF NOT EXISTS idx_feedback_rating_source
ON feedback_rating(feedback_source);
