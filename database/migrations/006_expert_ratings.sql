-- Migration 006: Expert rating table for psychometric validation
-- Stores gold-standard skill judgments from domain experts per dimension.

CREATE TABLE IF NOT EXISTS expert_rating (
    id               SERIAL PRIMARY KEY,
    rater_id         VARCHAR(16) NOT NULL,
    participant_code VARCHAR(16) NOT NULL,
    round_no         INTEGER NOT NULL,
    dimension        VARCHAR(32) NOT NULL,
    score            REAL NOT NULL CHECK (score >= 0 AND score <= 100),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (rater_id, participant_code, round_no, dimension)
);

CREATE INDEX IF NOT EXISTS idx_expert_rating_dimension
ON expert_rating(dimension);

CREATE INDEX IF NOT EXISTS idx_expert_rating_participant
ON expert_rating(participant_code);
