ALTER TABLE participant_feedback
ADD COLUMN IF NOT EXISTS favorite_part TEXT,
ADD COLUMN IF NOT EXISTS improvement_point TEXT,
ADD COLUMN IF NOT EXISTS comments TEXT;
