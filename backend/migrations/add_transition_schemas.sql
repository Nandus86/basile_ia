-- Migration: Add transition_input_schema and transition_output_schema to agents table
-- These JSON columns store data structures bypassed by the LLM Context used for metadata routing.

-- 1. Add transition_input_schema column
ALTER TABLE agents ADD COLUMN IF NOT EXISTS transition_input_schema JSON;

-- 2. Add transition_output_schema column
ALTER TABLE agents ADD COLUMN IF NOT EXISTS transition_output_schema JSON;

-- Verify
SELECT column_name, data_type FROM information_schema.columns 
WHERE table_name = 'agents' AND column_name IN ('transition_input_schema', 'transition_output_schema');
