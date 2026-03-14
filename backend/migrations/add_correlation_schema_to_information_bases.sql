-- Migration to add correlation_schema to information_bases table
ALTER TABLE information_bases ADD COLUMN IF NOT EXISTS correlation_schema JSONB;
