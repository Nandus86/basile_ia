-- Migration: Add Smart Queue Routing columns to dispatcher_configs
-- Date: 2026-05-14
-- Description: Adds routing rules, daily limit, and accumulation timer for weighted round-robin dispatch

ALTER TABLE dispatcher_configs
    ADD COLUMN IF NOT EXISTS queue_routing_rules JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS daily_message_limit INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS routing_accumulation_seconds INTEGER DEFAULT 60;

-- Ensure existing rows have defaults
UPDATE dispatcher_configs
SET queue_routing_rules = '[]'::jsonb
WHERE queue_routing_rules IS NULL;

UPDATE dispatcher_configs
SET daily_message_limit = 0
WHERE daily_message_limit IS NULL;

UPDATE dispatcher_configs
SET routing_accumulation_seconds = 60
WHERE routing_accumulation_seconds IS NULL;
