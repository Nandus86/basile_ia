-- Migration: Medium-Term Memory (MTM) — conversation_messages table
-- Version: 0.0.10

CREATE TABLE IF NOT EXISTS conversation_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    session_id VARCHAR NOT NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conv_msg_agent_session 
    ON conversation_messages(agent_id, session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_conv_msg_session 
    ON conversation_messages(session_id, created_at);
