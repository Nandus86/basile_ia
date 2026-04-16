-- Add new horizontal collaboration statuses
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'collaborationstatus') THEN
        -- SQLAlchemy Enum(YourEnum) persists enum member NAME by default
        -- so DB enum labels must include uppercase names.
        ALTER TYPE collaborationstatus ADD VALUE IF NOT EXISTS 'ALWAYS_ACTIVE_START';
        ALTER TYPE collaborationstatus ADD VALUE IF NOT EXISTS 'ALWAYS_ACTIVE_END';

        -- Compatibility in case lowercase values were added manually before
        ALTER TYPE collaborationstatus ADD VALUE IF NOT EXISTS 'always_active_start';
        ALTER TYPE collaborationstatus ADD VALUE IF NOT EXISTS 'always_active_end';
    END IF;
END $$;