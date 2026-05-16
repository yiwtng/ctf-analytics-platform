CREATE INDEX IF NOT EXISTS idx_feedback_reports_user_key
ON feedback_reports(user_key);

CREATE INDEX IF NOT EXISTS idx_feedback_reports_challenge_id
ON feedback_reports(challenge_id);

CREATE INDEX IF NOT EXISTS idx_feedback_reports_session_id
ON feedback_reports(session_id);

CREATE INDEX IF NOT EXISTS idx_feedback_reports_ts
ON feedback_reports(ts);
