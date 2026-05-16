-- Migration 008: Data integrity safeguards for research reproducibility
-- Append-only events table + data collection audit log

-- 1. Prevent UPDATE/DELETE on events (research integrity)
CREATE OR REPLACE FUNCTION prevent_event_mutation()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'events are append-only (research integrity) — UPDATE/DELETE not permitted';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS no_event_update ON events;
CREATE TRIGGER no_event_update
  BEFORE UPDATE OR DELETE ON events
  FOR EACH ROW EXECUTE FUNCTION prevent_event_mutation();

-- 2. Data collection milestone log
CREATE TABLE IF NOT EXISTS data_collection_log (
  id          SERIAL PRIMARY KEY,
  round_no    INTEGER,
  event_type  VARCHAR(64) NOT NULL,
  detail      JSONB,
  logged_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_data_collection_log_round ON data_collection_log (round_no);
CREATE INDEX IF NOT EXISTS idx_data_collection_log_type  ON data_collection_log (event_type);
