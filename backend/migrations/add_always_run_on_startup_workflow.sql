-- Adiciona a coluna always_run_on_startup na tabela workflows
ALTER TABLE workflows ADD COLUMN IF NOT EXISTS always_run_on_startup BOOLEAN DEFAULT FALSE;
