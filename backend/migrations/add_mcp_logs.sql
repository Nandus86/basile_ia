CREATE TABLE IF NOT EXISTS mcp_execution_logs (
    id UUID PRIMARY KEY,
    mcp_id UUID NULL,
    mcp_name VARCHAR NULL,
    protocol VARCHAR NULL,
    endpoint VARCHAR NULL,
    request_params JSONB NULL,
    response_data JSONB NULL,
    status VARCHAR NULL,
    error_message TEXT NULL,
    duration_ms DOUBLE PRECISION NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() at time zone 'utc')
);

CREATE INDEX IF NOT EXISTS ix_mcp_execution_logs_mcp_id ON mcp_execution_logs (mcp_id);
CREATE INDEX IF NOT EXISTS ix_mcp_execution_logs_id ON mcp_execution_logs (id);
