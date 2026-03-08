-- Migration to add MCP Groups (Folders) functionality

-- 1. Create the new mcp_groups table
CREATE TABLE IF NOT EXISTS mcp_groups (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Add group_id to mcps table
ALTER TABLE mcps ADD COLUMN IF NOT EXISTS group_id UUID REFERENCES mcp_groups(id) ON DELETE SET NULL;
