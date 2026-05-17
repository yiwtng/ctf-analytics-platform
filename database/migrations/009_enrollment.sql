-- Migration 009: Participant enrollment and pre/post assessment
-- Tracks IRB-approved enrollment lifecycle (consented → assigned → active → completed/withdrawn)

CREATE TABLE IF NOT EXISTS participant_enrollment (
    participant_code  VARCHAR(16)  PRIMARY KEY,
    ctfd_user_id      INTEGER      UNIQUE NOT NULL,
    source_group      VARCHAR(32)  NOT NULL,
    age_range         VARCHAR(16)  NOT NULL,
    education_level   VARCHAR(32)  NOT NULL,
    experience_level  VARCHAR(16)  NOT NULL,
    irb_study_id      VARCHAR(64)  NOT NULL,
    consent_recorded  TIMESTAMPTZ  NOT NULL,
    status            VARCHAR(32)  NOT NULL DEFAULT 'consented',
    enrolled_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    withdrawn_at      TIMESTAMPTZ,
    CHECK (status IN ('pending_consent','consented','pre_tested','assigned',
                      'active','completed','withdrawn'))
);

CREATE INDEX IF NOT EXISTS idx_enroll_status ON participant_enrollment (status);
CREATE INDEX IF NOT EXISTS idx_enroll_source ON participant_enrollment (source_group);

CREATE TABLE IF NOT EXISTS participant_assessment (
    id                SERIAL       PRIMARY KEY,
    participant_code  VARCHAR(16)  NOT NULL,
    assessment_type   VARCHAR(16)  NOT NULL CHECK (assessment_type IN ('pretest','posttest')),
    score             REAL         NOT NULL,
    max_score         REAL         NOT NULL CHECK (max_score > 0),
    administered_at   TIMESTAMPTZ  NOT NULL,
    UNIQUE (participant_code, assessment_type)
);

CREATE INDEX IF NOT EXISTS idx_assessment_code ON participant_assessment (participant_code);
