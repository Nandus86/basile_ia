-- Migration to add Agent MCP Group Access table
-- 1. Create agent_mcp_group_access association table
CREATE TABLE IF NOT EXISTS agent_mcp_group_access (
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    mcp_group_id UUID NOT NULL REFERENCES mcp_groups(id) ON DELETE CASCADE,
    PRIMARY KEY (agent_id, mcp_group_id)
);
