ALTER TABLE agents
ADD COLUMN IF NOT EXISTS true_trigger_keywords JSON DEFAULT '[]'::json,
ADD COLUMN IF NOT EXISTS true_trigger_match_mode VARCHAR(20) NOT NULL DEFAULT 'word';
