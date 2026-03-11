-- ============================================================
-- Migration: RAG 3.0 - VFS Knowledge Bases
-- Version: 0.0.8
-- Date: 2026-03-11
-- ============================================================

-- 1. Tabela principal: vfs_knowledge_bases
CREATE TABLE IF NOT EXISTS vfs_knowledge_bases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    vfs_path VARCHAR(500) NOT NULL,
    file_count INTEGER DEFAULT 0,
    total_size_bytes INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Tabela de arquivos: vfs_files
CREATE TABLE IF NOT EXISTS vfs_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    knowledge_base_id UUID NOT NULL REFERENCES vfs_knowledge_bases(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    title VARCHAR(500),
    file_path VARCHAR(500) NOT NULL,
    size_bytes INTEGER DEFAULT 0,
    summary TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vfs_files_knowledge_base_id ON vfs_files(knowledge_base_id);

-- 3. Tabela de associação: agent <-> vfs_knowledge_base (many-to-many)
CREATE TABLE IF NOT EXISTS agent_vfs_knowledge_base_access (
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    knowledge_base_id UUID NOT NULL REFERENCES vfs_knowledge_bases(id) ON DELETE CASCADE,
    PRIMARY KEY (agent_id, knowledge_base_id)
);
