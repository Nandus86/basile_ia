-- Migration: add_outbound_mode
-- Branch: 0.0.87
-- Description: Adds outbound_mode and ai_formulation_prompt to dispatcher_configs.
--              outbound_mode controls how the dispatched message is recorded in the
--              agent's conversation history:
--                "agent"         → default behaviour (treated as HumanMessage)
--                "bypass"        → message recorded as AIMessage (assistant) without invoking the agent
--                "ai_formulated" → agent formulates the text; recorded as AIMessage (assistant)

ALTER TABLE dispatcher_configs
    ADD COLUMN IF NOT EXISTS outbound_mode VARCHAR(20) NOT NULL DEFAULT 'agent',
    ADD COLUMN IF NOT EXISTS ai_formulation_prompt VARCHAR(2000) NULL;

-- Ensure existing rows keep the default behaviour
UPDATE dispatcher_configs
SET outbound_mode = 'agent'
WHERE outbound_mode IS NULL OR outbound_mode = '';
