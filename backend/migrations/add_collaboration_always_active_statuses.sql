-- Add new horizontal collaboration statuses
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'collaborationstatus') THEN
        ALTER TYPE collaborationstatus ADD VALUE IF NOT EXISTS 'always_active_start';
        ALTER TYPE collaborationstatus ADD VALUE IF NOT EXISTS 'always_active_end';
    END IF;
END $$;