-- Adiciona a coluna always_run_on_startup na tabela mcps
ALTER TABLE mcps ADD COLUMN IF NOT EXISTS always_run_on_startup BOOLEAN DEFAULT FALSE;
