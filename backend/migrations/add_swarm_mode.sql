-- Add swarm_mode column to agents table
ALTER TABLE agents ADD COLUMN IF NOT EXISTS swarm_mode BOOLEAN NOT NULL DEFAULT FALSE;
