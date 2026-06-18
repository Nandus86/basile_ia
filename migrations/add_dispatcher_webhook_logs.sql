-- Migration: Add dispatcher_webhook_logs table
-- Target: Postgres database
-- Executed on: 2026-06-18

CREATE TABLE IF NOT EXISTS dispatcher_webhook_logs (
    id UUID PRIMARY KEY,
    webhook_path VARCHAR(255) NOT NULL,
    status_code INTEGER,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    request_payload JSONB,
    response_payload JSONB,
    error_message TEXT,
    contact_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    duration_ms INTEGER
);

CREATE INDEX IF NOT EXISTS idx_dispatcher_webhook_logs_path ON dispatcher_webhook_logs(webhook_path);
CREATE INDEX IF NOT EXISTS idx_dispatcher_webhook_logs_status ON dispatcher_webhook_logs(status);
CREATE INDEX IF NOT EXISTS idx_dispatcher_webhook_logs_created ON dispatcher_webhook_logs(created_at DESC);
