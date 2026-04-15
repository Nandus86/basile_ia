-- Add global information base search flag to agents table
ALTER TABLE agents
ADD COLUMN IF NOT EXISTS information_bases_global_search_enabled BOOLEAN NOT NULL DEFAULT FALSE;
