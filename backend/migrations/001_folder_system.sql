/*
  SQL Migration: Folder System for Skills and Agents
  Execute this ONCE on your PostgreSQL database before starting the app.
*/

-- 1. Skill Groups (flat folders)
CREATE TABLE IF NOT EXISTS skill_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE skills ADD COLUMN IF NOT EXISTS group_id UUID REFERENCES skill_groups(id) ON DELETE SET NULL;

-- 2. Agent Groups (hierarchical folders with sub-folders)
CREATE TABLE IF NOT EXISTS agent_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    parent_id UUID REFERENCES agent_groups(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE agents ADD COLUMN IF NOT EXISTS group_id UUID REFERENCES agent_groups(id) ON DELETE SET NULL;
