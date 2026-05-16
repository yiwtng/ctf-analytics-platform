CREATE TABLE IF NOT EXISTS ai_reports (
    ai_report_id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    ts TIMESTAMP NOT NULL DEFAULT NOW(),
    user_key TEXT NOT NULL,
    model_name TEXT,
    raw_summary JSONB NOT NULL,
    ai_report JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_reports_user_key
ON ai_reports(user_key);

CREATE INDEX IF NOT EXISTS idx_ai_reports_ts
ON ai_reports(ts);