-- Migration: Add strict_retry_message column to workflows table
ALTER TABLE workflows ADD COLUMN IF NOT EXISTS strict_retry_message TEXT DEFAULT 'Estamos com instabilidade, vamos iniciar novamente.';
