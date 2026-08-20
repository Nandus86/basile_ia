-- Migration: Add auto_dispatch_mapping to analytics_config
-- Description: Armazena o mapeamento de endpoints e type_ids para quantificação de disparos automáticos nos relatórios

ALTER TABLE analytics_config 
ADD COLUMN IF NOT EXISTS auto_dispatch_mapping JSONB DEFAULT '[]'::jsonb;

UPDATE analytics_config
SET auto_dispatch_mapping = '[]'::jsonb
WHERE auto_dispatch_mapping IS NULL;
