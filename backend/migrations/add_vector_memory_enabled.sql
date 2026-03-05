-- Add vector_memory_enabled column to agents table
ALTER TABLE agents
ADD COLUMN IF NOT EXISTS vector_memory_enabled BOOLEAN NOT NULL DEFAULT FALSE;
