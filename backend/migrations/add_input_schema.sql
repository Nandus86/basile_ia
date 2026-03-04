-- Migration: Add input_schema column to agents table
-- This column stores a JSON schema defining the expected context_data fields for an agent.
-- Run this migration against your PostgreSQL database.

ALTER TABLE agents ADD COLUMN IF NOT EXISTS input_schema JSON DEFAULT NULL;

-- Verify
SELECT column_name, data_type FROM information_schema.columns 
WHERE table_name = 'agents' AND column_name = 'input_schema';
