-- Migration 005: Experiment assignment table for control/treatment randomization
-- Implements block randomization for the CTF skill-feedback study.

CREATE TABLE IF NOT EXISTS experiment_assignment (
    user_id      INTEGER PRIMARY KEY,
    condition    VARCHAR(16) NOT NULL CHECK (condition IN ('control', 'treatment')),
    block_id     INTEGER NOT NULL,
    seed         INTEGER NOT NULL,
    assigned_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_exp_condition ON experiment_assignment(condition);
