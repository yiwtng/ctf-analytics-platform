-- Migration 013: Item-level storage for participant questionnaires.
--
-- WHY participant_feedback is not enough
-- That table holds four fixed Likert columns (usability, challenge quality,
-- recommendation quality, confidence improvement). Four single-item ratings
-- cannot carry a multi-item scale, and without item-level responses the internal
-- consistency of the scale itself cannot be computed -- so a self-efficacy score
-- derived from it could not be shown to be reliable, which is precisely what H3
-- needs. Adding more columns per item would also mean a migration every time an
-- item is reworded.
--
-- Long format instead: one row per (participant, round, instrument, item). This
-- stores any instrument without further schema changes, keeps item wording
-- versioned alongside the response, and lets alpha be computed directly.
--
-- participant_feedback is left in place: it already backs the admin feedback page
-- and the four ratings remain useful as single-item satisfaction measures.

CREATE TABLE IF NOT EXISTS survey_response (
    id               SERIAL      PRIMARY KEY,
    participant_code VARCHAR(16) NOT NULL,
    round_no         INTEGER,
    instrument       VARCHAR(32) NOT NULL,
    instrument_ver   VARCHAR(16) NOT NULL DEFAULT 'v1',
    item_code        VARCHAR(32) NOT NULL,
    -- Response scales differ by instrument (0-100 confidence for the
    -- self-efficacy scale, 1-5 Likert for satisfaction), so the admissible range
    -- is recorded per row rather than assumed.
    response         NUMERIC(6,2) NOT NULL,
    scale_min        NUMERIC(6,2) NOT NULL,
    scale_max        NUMERIC(6,2) NOT NULL,
    -- 'pre' or 'post' for instruments administered twice within a round.
    occasion         VARCHAR(8),
    responded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT survey_response_round_check
        CHECK (round_no IS NULL OR round_no BETWEEN 1 AND 3),
    CONSTRAINT survey_response_range_check
        CHECK (response >= scale_min AND response <= scale_max),
    CONSTRAINT survey_response_scale_check
        CHECK (scale_max > scale_min),
    CONSTRAINT survey_response_occasion_check
        CHECK (occasion IS NULL OR occasion IN ('pre', 'post')),

    -- One response per item per occasion. Re-submission is idempotent rather
    -- than duplicating, so a participant refreshing the form cannot inflate n.
    CONSTRAINT survey_response_unique
        UNIQUE (participant_code, round_no, instrument, item_code, occasion)
);

COMMENT ON TABLE survey_response IS
    'Item-level questionnaire responses in long format; supports scale reliability analysis';
COMMENT ON COLUMN survey_response.instrument IS
    'Instrument identifier, e.g. cse (cybersecurity self-efficacy), sat (satisfaction)';
COMMENT ON COLUMN survey_response.instrument_ver IS
    'Version of the item wording, so a mid-study revision remains distinguishable';
COMMENT ON COLUMN survey_response.occasion IS
    'pre | post for instruments administered before and after a round; NULL otherwise';

CREATE INDEX IF NOT EXISTS idx_survey_response_participant
ON survey_response(participant_code);

CREATE INDEX IF NOT EXISTS idx_survey_response_instrument
ON survey_response(instrument, instrument_ver, round_no);
