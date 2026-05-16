-- Migration 007: Expert ratings for AI feedback quality
-- Captures relevance, actionability, and accuracy scores from domain experts
-- for each AI-generated feedback report.

CREATE TABLE IF NOT EXISTS feedback_rating (
    id               SERIAL PRIMARY KEY,
    rater_id         VARCHAR(16) NOT NULL,
    participant_code VARCHAR(16) NOT NULL,
    round_no         INTEGER NOT NULL,
    relevance        SMALLINT NOT NULL CHECK (relevance BETWEEN 1 AND 5),
    actionability    SMALLINT NOT NULL CHECK (actionability BETWEEN 1 AND 5),
    accuracy         SMALLINT NOT NULL CHECK (accuracy BETWEEN 1 AND 5),
    comment          TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (rater_id, participant_code, round_no)
);

CREATE INDEX IF NOT EXISTS idx_feedback_rating_participant
ON feedback_rating(participant_code);
