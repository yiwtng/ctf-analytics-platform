CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS participant_feedback (
    feedback_id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    ts TIMESTAMP NOT NULL DEFAULT NOW(),
    user_key TEXT NOT NULL,

    usability_score INT CHECK (usability_score BETWEEN 1 AND 5),
    challenge_quality_score INT CHECK (challenge_quality_score BETWEEN 1 AND 5),
    recommendation_quality_score INT CHECK (recommendation_quality_score BETWEEN 1 AND 5),
    confidence_improvement_score INT CHECK (confidence_improvement_score BETWEEN 1 AND 5),

    favorite_part TEXT,
    improvement_point TEXT,
    comments TEXT
);

CREATE INDEX IF NOT EXISTS idx_participant_feedback_user_key
ON participant_feedback(user_key);

CREATE INDEX IF NOT EXISTS idx_participant_feedback_ts
ON participant_feedback(ts);
