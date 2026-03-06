CREATE TABLE IF NOT EXISTS information_bases (
    id UUID PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(100) NOT NULL UNIQUE,
    content_schema JSONB,
    metadata_schema JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_information_bases_code ON information_bases (code);

CREATE TABLE IF NOT EXISTS agent_info_base_access (
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    information_base_id UUID REFERENCES information_bases(id) ON DELETE CASCADE,
    PRIMARY KEY (agent_id, information_base_id)
);
