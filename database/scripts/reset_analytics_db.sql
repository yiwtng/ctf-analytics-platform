-- =============================================================================
-- ANALYTICS DB RESET SCRIPT
-- =============================================================================
-- PURPOSE: Clean slate before IRB-approved data collection begins (June 2026).
-- This script drops ALL analytics data and recreates the schema from scratch.
--
-- USAGE: Called only by tools/setup/reset_for_data_collection.sh
-- DO NOT run manually against a production DB containing real participant data.
-- =============================================================================

-- Drop all tables (CASCADE removes dependent indexes, triggers, constraints)
DROP TABLE IF EXISTS data_collection_log   CASCADE;
DROP TABLE IF EXISTS feedback_rating       CASCADE;
DROP TABLE IF EXISTS expert_rating         CASCADE;
DROP TABLE IF EXISTS experiment_assignment CASCADE;
DROP TABLE IF EXISTS user_ai_reports       CASCADE;
DROP TABLE IF EXISTS user_skill_reports    CASCADE;
DROP TABLE IF EXISTS participant_feedback  CASCADE;
DROP TABLE IF EXISTS features              CASCADE;
DROP TABLE IF EXISTS events                CASCADE;
DROP TABLE IF EXISTS feedback_reports      CASCADE;

-- Drop functions
DROP FUNCTION IF EXISTS prevent_event_mutation CASCADE;

-- =========================================================
-- Recreate base schema (000–004)
-- =========================================================

-- events (core telemetry)
CREATE TABLE IF NOT EXISTS events (
    event_id     UUID         NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    ts           TIMESTAMP    NOT NULL DEFAULT now(),
    user_key     TEXT,
    team_key     TEXT,
    challenge_id TEXT,
    session_id   TEXT,
    event_type   TEXT         NOT NULL,
    source       TEXT,
    payload      JSONB        NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_events_user_key     ON events (user_key);
CREATE INDEX idx_events_ts           ON events (ts);
CREATE INDEX idx_events_event_type   ON events (event_type);
CREATE INDEX idx_events_session_id   ON events (session_id);
CREATE INDEX idx_events_challenge_id ON events (challenge_id);

-- participant_feedback (post-round survey)
CREATE TABLE IF NOT EXISTS participant_feedback (
    feedback_id                  UUID     NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    ts                           TIMESTAMP NOT NULL DEFAULT now(),
    user_key                     TEXT     NOT NULL,
    usability_score              INTEGER  CHECK (usability_score BETWEEN 1 AND 5),
    challenge_quality_score      INTEGER  CHECK (challenge_quality_score BETWEEN 1 AND 5),
    recommendation_quality_score INTEGER  CHECK (recommendation_quality_score BETWEEN 1 AND 5),
    confidence_improvement_score INTEGER  CHECK (confidence_improvement_score BETWEEN 1 AND 5),
    favorite_part                TEXT,
    improvement_point            TEXT,
    comments                     TEXT
);

CREATE INDEX idx_participant_feedback_user_key ON participant_feedback (user_key);
CREATE INDEX idx_participant_feedback_ts       ON participant_feedback (ts);

-- features (computed features per session)
CREATE TABLE IF NOT EXISTS features (
    id         SERIAL  PRIMARY KEY,
    user_key   TEXT    NOT NULL,
    session_id TEXT,
    ts         TIMESTAMP NOT NULL DEFAULT now(),
    payload    JSONB   NOT NULL DEFAULT '{}'
);

-- user_skill_reports (skill score snapshots)
CREATE TABLE IF NOT EXISTS user_skill_reports (
    id                    SERIAL    PRIMARY KEY,
    user_key              TEXT      NOT NULL,
    generated_at          TIMESTAMP NOT NULL DEFAULT now(),
    total_opened          INTEGER   NOT NULL DEFAULT 0,
    total_started         INTEGER   NOT NULL DEFAULT 0,
    total_ready           INTEGER   NOT NULL DEFAULT 0,
    total_solves          INTEGER   NOT NULL DEFAULT 0,
    total_wrong_submits   INTEGER   NOT NULL DEFAULT 0,
    total_giveups         INTEGER   NOT NULL DEFAULT 0,
    total_errors          INTEGER   NOT NULL DEFAULT 0,
    web_recon_score       INTEGER   NOT NULL DEFAULT 0,
    protocol_score        INTEGER   NOT NULL DEFAULT 0,
    ssh_pivot_score       INTEGER   NOT NULL DEFAULT 0,
    blue_analysis_score   INTEGER   NOT NULL DEFAULT 0,
    accuracy_score        INTEGER   NOT NULL DEFAULT 0,
    persistence_score     INTEGER   NOT NULL DEFAULT 0,
    time_efficiency_score INTEGER   NOT NULL DEFAULT 0
);

CREATE INDEX idx_user_skill_reports_user_key ON user_skill_reports (user_key);

-- user_ai_reports (LLM-generated feedback)
CREATE TABLE IF NOT EXISTS user_ai_reports (
    id            SERIAL    PRIMARY KEY,
    user_key      TEXT      NOT NULL,
    generated_at  TIMESTAMP NOT NULL DEFAULT now(),
    model_name    TEXT,
    profile       JSONB,
    strengths     JSONB,
    weaknesses    JSONB,
    recommendations JSONB,
    summary       TEXT,
    confidence    TEXT,
    raw_summary   JSONB,
    ai_report     JSONB,
    raw_response  JSONB,
    model         TEXT
);

CREATE INDEX idx_user_ai_reports_user_key ON user_ai_reports (user_key);

-- feedback_reports (legacy)
CREATE TABLE IF NOT EXISTS feedback_reports (
    id       SERIAL PRIMARY KEY,
    user_key TEXT   NOT NULL,
    ts       TIMESTAMP NOT NULL DEFAULT now(),
    payload  JSONB  NOT NULL DEFAULT '{}'
);

-- =========================================================
-- Migrations 005–008
-- =========================================================

-- 005: experiment_assignment
CREATE TABLE IF NOT EXISTS experiment_assignment (
    user_id     INTEGER     PRIMARY KEY,
    condition   VARCHAR(16) NOT NULL CHECK (condition IN ('control','treatment')),
    block_id    INTEGER     NOT NULL,
    seed        INTEGER     NOT NULL,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_exp_assignment_condition ON experiment_assignment (condition);

-- 006: expert_rating
CREATE TABLE IF NOT EXISTS expert_rating (
    id               SERIAL      PRIMARY KEY,
    rater_id         TEXT        NOT NULL,
    participant_code TEXT        NOT NULL,
    round_no         INTEGER     NOT NULL,
    dimension        TEXT        NOT NULL,
    score            NUMERIC(5,2) NOT NULL CHECK (score BETWEEN 0 AND 100),
    notes            TEXT,
    rated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (rater_id, participant_code, round_no, dimension)
);

CREATE INDEX IF NOT EXISTS idx_expert_rating_code  ON expert_rating (participant_code);
CREATE INDEX IF NOT EXISTS idx_expert_rating_rater ON expert_rating (rater_id);

-- 007: feedback_rating (AI feedback quality)
CREATE TABLE IF NOT EXISTS feedback_rating (
    id               SERIAL      PRIMARY KEY,
    rater_id         TEXT        NOT NULL,
    participant_code TEXT        NOT NULL,
    round_no         INTEGER     NOT NULL,
    relevance        INTEGER     NOT NULL CHECK (relevance BETWEEN 1 AND 5),
    specificity      INTEGER     NOT NULL CHECK (specificity BETWEEN 1 AND 5),
    actionability    INTEGER     NOT NULL CHECK (actionability BETWEEN 1 AND 5),
    accuracy         INTEGER     NOT NULL CHECK (accuracy BETWEEN 1 AND 5),
    rated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feedback_rating_code ON feedback_rating (participant_code);

-- 008: append-only trigger + data_collection_log
CREATE OR REPLACE FUNCTION prevent_event_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'events are append-only (research integrity) — UPDATE/DELETE not permitted';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER no_event_update
    BEFORE UPDATE OR DELETE ON events
    FOR EACH ROW EXECUTE FUNCTION prevent_event_mutation();

CREATE TABLE IF NOT EXISTS data_collection_log (
    id         SERIAL      PRIMARY KEY,
    round_no   INTEGER,
    event_type VARCHAR(64) NOT NULL,
    detail     JSONB,
    logged_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_data_collection_log_round ON data_collection_log (round_no);
CREATE INDEX IF NOT EXISTS idx_data_collection_log_type  ON data_collection_log (event_type);

-- =========================================================
-- Initial provenance record
-- =========================================================
INSERT INTO data_collection_log (event_type, detail)
VALUES (
    'db_initialized',
    '{"detail": "clean slate for IRB-approved collection", "source": "reset_for_data_collection.sh"}'::jsonb
);
