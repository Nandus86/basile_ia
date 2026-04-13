-- ============================================================
-- MIGRAÇÃO COMPLETA: 0.0.32 → 0.0.37
-- Execute no banco de produção (PostgreSQL)
-- Cada comando verifica se já existe antes de executar
-- ============================================================

-- ============================================================
-- 1. SKILLS: campo always_active (desde 0.0.33)
-- ============================================================
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='skills' AND column_name='always_active'
    ) THEN
        ALTER TABLE skills ADD COLUMN always_active BOOLEAN DEFAULT FALSE;
        RAISE NOTICE '✅ skills.always_active adicionado';
    ELSE
        RAISE NOTICE '⏭️ skills.always_active já existe';
    END IF;
END $$;

-- ============================================================
-- 2. AI PROVIDER: campo provider_id nos agents (desde 0.0.35)
-- ============================================================
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='agents' AND column_name='provider_id'
    ) THEN
        ALTER TABLE agents ADD COLUMN provider_id UUID;
        ALTER TABLE agents 
            ADD CONSTRAINT fk_agent_provider 
            FOREIGN KEY (provider_id) 
            REFERENCES ai_providers(id) 
            ON DELETE SET NULL;
        RAISE NOTICE '✅ agents.provider_id adicionado com FK';
    ELSE
        RAISE NOTICE '⏭️ agents.provider_id já existe';
    END IF;
END $$;

-- ============================================================
-- 3. DISPATCHER: tabela dispatcher_configs (desde 0.0.34)
-- ============================================================
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_name='dispatcher_configs'
    ) THEN
        CREATE TABLE dispatcher_configs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            path VARCHAR(255) NOT NULL UNIQUE,
            api_key VARCHAR(500),
            buttons_enabled BOOLEAN DEFAULT FALSE,
            buttons JSON DEFAULT '[]'::json,
            image_enabled BOOLEAN DEFAULT FALSE,
            messages_per_batch INTEGER DEFAULT 1,
            agent_id UUID REFERENCES agents(id) ON DELETE SET NULL,
            start_time VARCHAR(5) DEFAULT '08:00',
            end_time VARCHAR(5) DEFAULT '22:00',
            start_delay_seconds INTEGER DEFAULT 0,
            min_variation_seconds INTEGER DEFAULT 5,
            max_variation_seconds INTEGER DEFAULT 15,
            triggers JSON DEFAULT '[]'::json,
            index_max INTEGER DEFAULT 5,
            progress_callback_url VARCHAR(500),
            target_endpoint VARCHAR(500),
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX idx_dispatcher_configs_path ON dispatcher_configs(path);
        RAISE NOTICE '✅ Tabela dispatcher_configs criada';
    ELSE
        RAISE NOTICE '⏭️ Tabela dispatcher_configs já existe';
    END IF;
END $$;

-- 3b. DISPATCHER: campo target_endpoint (desde 0.0.35)
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables WHERE table_name='dispatcher_configs'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='dispatcher_configs' AND column_name='target_endpoint'
    ) THEN
        ALTER TABLE dispatcher_configs ADD COLUMN target_endpoint VARCHAR(500);
        RAISE NOTICE '✅ dispatcher_configs.target_endpoint adicionado';
    ELSE
        RAISE NOTICE '⏭️ dispatcher_configs.target_endpoint já existe ou tabela não existe';
    END IF;
END $$;

-- ============================================================
-- 4. THINKER: campos no agents (desde 0.0.37)
-- ============================================================
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='agents' AND column_name='is_thinker'
    ) THEN
        ALTER TABLE agents ADD COLUMN is_thinker BOOLEAN DEFAULT FALSE NOT NULL;
        RAISE NOTICE '✅ agents.is_thinker adicionado';
    ELSE
        RAISE NOTICE '⏭️ agents.is_thinker já existe';
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='agents' AND column_name='thinker_prompt'
    ) THEN
        ALTER TABLE agents ADD COLUMN thinker_prompt TEXT;
        RAISE NOTICE '✅ agents.thinker_prompt adicionado';
    ELSE
        RAISE NOTICE '⏭️ agents.thinker_prompt já existe';
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='agents' AND column_name='thinker_model'
    ) THEN
        ALTER TABLE agents ADD COLUMN thinker_model VARCHAR(100);
        RAISE NOTICE '✅ agents.thinker_model adicionado';
    ELSE
        RAISE NOTICE '⏭️ agents.thinker_model já existe';
    END IF;
END $$;

-- ============================================================
-- 5. THINKER LINKS: tabela de relacionamento (desde 0.0.37)
-- ============================================================
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_name='agent_thinker_links'
    ) THEN
        CREATE TABLE agent_thinker_links (
            agent_id UUID NOT NULL,
            thinker_id UUID NOT NULL,
            is_active BOOLEAN DEFAULT TRUE NOT NULL,
            PRIMARY KEY (agent_id, thinker_id),
            FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE,
            FOREIGN KEY (thinker_id) REFERENCES agents(id) ON DELETE CASCADE
        );
        RAISE NOTICE '✅ Tabela agent_thinker_links criada';
    ELSE
        RAISE NOTICE '⏭️ Tabela agent_thinker_links já existe';
    END IF;
END $$;

-- ============================================================
-- VERIFICAÇÃO FINAL
-- ============================================================
SELECT '=== VERIFICAÇÃO ===' as status;

SELECT 'agents.provider_id' as campo, 
       CASE WHEN EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='agents' AND column_name='provider_id') 
            THEN '✅ OK' ELSE '❌ FALTANDO' END as resultado
UNION ALL
SELECT 'agents.is_thinker',
       CASE WHEN EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='agents' AND column_name='is_thinker') 
            THEN '✅ OK' ELSE '❌ FALTANDO' END
UNION ALL
SELECT 'agents.thinker_prompt',
       CASE WHEN EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='agents' AND column_name='thinker_prompt') 
            THEN '✅ OK' ELSE '❌ FALTANDO' END
UNION ALL
SELECT 'agents.thinker_model',
       CASE WHEN EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='agents' AND column_name='thinker_model') 
            THEN '✅ OK' ELSE '❌ FALTANDO' END
UNION ALL
SELECT 'skills.always_active',
       CASE WHEN EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='skills' AND column_name='always_active') 
            THEN '✅ OK' ELSE '❌ FALTANDO' END
UNION ALL
SELECT 'tabela agent_thinker_links',
       CASE WHEN EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='agent_thinker_links') 
            THEN '✅ OK' ELSE '❌ FALTANDO' END
UNION ALL
SELECT 'tabela dispatcher_configs',
       CASE WHEN EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='dispatcher_configs') 
            THEN '✅ OK' ELSE '❌ FALTANDO' END;
