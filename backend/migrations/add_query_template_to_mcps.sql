-- Migration: add_query_template_to_mcps

ALTER TABLE mcps ADD COLUMN IF NOT EXISTS query_template JSONB DEFAULT '{}'::jsonb;
