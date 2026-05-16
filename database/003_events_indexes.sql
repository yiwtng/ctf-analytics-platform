CREATE INDEX IF NOT EXISTS idx_events_user_key
ON events(user_key);

CREATE INDEX IF NOT EXISTS idx_events_challenge_id
ON events(challenge_id);

CREATE INDEX IF NOT EXISTS idx_events_session_id
ON events(session_id);

CREATE INDEX IF NOT EXISTS idx_events_event_type
ON events(event_type);

CREATE INDEX IF NOT EXISTS idx_events_ts
ON events(ts);
