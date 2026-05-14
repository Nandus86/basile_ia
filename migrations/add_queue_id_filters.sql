-- Migration: Add queue_id filter columns to dispatcher_configs
-- Date: 2026-05-14
-- Description: Adds blocklist and allowlist columns for queue_id filtering

ALTER TABLE dispatcher_configs
    ADD COLUMN IF NOT EXISTS queue_id_blocklist JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS queue_id_allowlist JSONB DEFAULT '[]'::jsonb;

-- Ensure existing rows have the default value
UPDATE dispatcher_configs
SET queue_id_blocklist = '[]'::jsonb
WHERE queue_id_blocklist IS NULL;

UPDATE dispatcher_configs
SET queue_id_allowlist = '[]'::jsonb
WHERE queue_id_allowlist IS NULL;
