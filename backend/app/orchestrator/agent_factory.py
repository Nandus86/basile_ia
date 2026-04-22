"""
Agent Factory - Creates LangGraph-compatible agents from database configurations
"""
from typing import List, Optional, Dict, Any, TypedDict
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import create_react_agent
from langgraph.graph import StateGraph, START, END
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.agent import Agent, AccessLevel, ExecutionMode, agent_thinker_links
from app.config import settings
from app.orchestrator.callbacks import build_cost_callbacks

import logging
import json
import copy
import urllib.parse
import hashlib
import time
from pydantic import BaseModel, Field
logger = logging.getLogger(__name__)



class ToolFirstPlan(BaseModel):
    """Structured plan for deterministic tool-first execution."""
    steps: List[str] = Field(default_factory=list)
    max_tool_calls: int = Field(default=3, ge=0, le=10)
    max_collab_calls: int = Field(default=1, ge=0, le=5)
    stop_condition: str = Field(default="respond_when_data_is_sufficient")


class ExecutionBudget:
    """Turn-level budget guardrails for deterministic execution."""

    def __init__(
        self,
        max_total_actions: int = 4,
        max_tool_calls: int = 3,
        max_collab_calls: int = 1,
        max_wall_time_seconds: int = 25,
    ):
        self.max_total_actions = max_total_actions
        self.max_tool_calls = max_tool_calls
        self.max_collab_calls = max_collab_calls
        self.max_wall_time_seconds = max_wall_time_seconds
        self.actions_used = 0
        self.tool_calls_used = 0
        self.collab_calls_used = 0
        self.started_at = time.monotonic()

    def can_continue(self) -> bool:
        if self.actions_used >= self.max_total_actions:
            return False
        if (time.monotonic() - self.started_at) >= self.max_wall_time_seconds:
            return False
        return True

    def consume(self, action_type: str) -> bool:
        if not self.can_continue():
            return False
        if action_type == "tool" and self.tool_calls_used >= self.max_tool_calls:
            return False
        if action_type == "collab" and self.collab_calls_used >= self.max_collab_calls:
            return False

        self.actions_used += 1
        if action_type == "tool":
            self.tool_calls_used += 1
        if action_type == "collab":
            self.collab_calls_used += 1
        return True

    def stop_reason(self) -> str:
        if self.actions_used >= self.max_total_actions:
            return "budget_exceeded"
        if self.tool_calls_used >= self.max_tool_calls:
            return "tool_budget_exceeded"
        if self.collab_calls_used >= self.max_collab_calls:
            return "collab_budget_exceeded"
        if (time.monotonic() - self.started_at) >= self.max_wall_time_seconds:
            return "timeout"
        return "completed"


class AgentRuntimeState(TypedDict, total=False):
    execution_mode: str
    actions_used: int
    tool_calls_used: int
    collab_calls_used: int
    seen_fingerprints: List[str]
    start_time: float


def _normalize_args(args: Any) -> str:
    try:
        return json.dumps(args or {}, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        return str(args)


def _fingerprint_tool_call(name: str, args: Any) -> str:
    raw = f"{name}:{_normalize_args(args)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AgentFactory:
    """
    Factory for creating LangGraph-compatible agents from database configurations.
    
    Each agent from the database is converted to a runnable that can be:
    - A simple LLM call (no tools)
    - A ReAct agent (with MCP tools)
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self._agent_cache: Dict[str, Dict[str, Any]] = {}
    
    async def get_accessible_agents(self, user_access_level: str = "normal") -> List[Agent]:
        """Get all agents accessible to a user based on access level"""
        try:
            user_level = AccessLevel(user_access_level)
        except ValueError:
            user_level = AccessLevel.NORMAL
        
        user_level_value = AccessLevel.get_level_value(user_level)
        
        result = await self.db.execute(
            select(Agent)
            .options(
                selectinload(Agent.mcps),
                selectinload(Agent.skills),
                selectinload(Agent.information_bases),
                selectinload(Agent.vfs_knowledge_bases),
                selectinload(Agent.provider),
            )
            .where(Agent.is_active == True)
        )
        all_agents = result.scalars().all()
        
        # Filter by access level
        accessible = [
            a for a in all_agents
            if AccessLevel.get_level_value(a.access_level) <= user_level_value
        ]
        
        return accessible
    
    async def get_agent_by_id(self, agent_id: str) -> Optional[Agent]:
        """Get a specific agent by ID with all relationships eagerly loaded"""
        result = await self.db.execute(
            select(Agent)
            .options(
                selectinload(Agent.mcps),
                selectinload(Agent.skills),
                selectinload(Agent.information_bases),
                selectinload(Agent.vfs_knowledge_bases),
                selectinload(Agent.collaborator_settings),
                selectinload(Agent.provider),
            )
            .where(Agent.id == agent_id, Agent.is_active == True)
        )
        return result.scalar_one_or_none()
    
    async def get_agent_config(self, agent: Agent, context_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Convert database agent to configuration dict"""
        agent_id = str(agent.id)
        
        # Check cache (only if no context data provided, or separate key?)
        # Since AgentFactory is per-request, cache is safe within request.
        if agent_id in self._agent_cache:
            return self._agent_cache[agent_id]
        
        # Filter context data based on agent's input_schema to prevent leakage
        from app.schemas.structured_output import filter_context_data
        filtered_context = filter_context_data(context_data, agent.input_schema)
        
        if context_data and filtered_context:
            logger.info(f"[AgentFactory] 🛡️ Context data filtrado para '{agent.name}': {list(filtered_context.keys())}")
        elif context_data and not filtered_context:
            logger.info(f"[AgentFactory] 🛡️ Context data TOTALMENTE filtrado (vazio) para '{agent.name}' (sem correspondência no schema)")
        
        # Load MCP tools
        tools = []
        try:
            from app.services.mcp_tools import get_tools_for_agent
            # Usamos o context_data ORIGINAL para as ferramentas pre-resolverem seus placeholders {{ $request }}
            # independentemente do input_schema do agente.
            tools = await get_tools_for_agent(self.db, agent_id, context_data)
            if tools:
                tool_names = [t.name for t in tools]
                logger.info(f"[AgentFactory] 🧰 Agent '{agent.name}' carregou {len(tools)} tool(s): {tool_names}")
            else:
                logger.info(f"[AgentFactory] 🧯 Agent '{agent.name}' sem tools (no tools loaded)")
        except Exception as e:
            logger.error(f"[AgentFactory] ❌ Falha ao carregar tools para '{agent.name}': {e}", exc_info=True)
        
        # Build system prompt with skills injection
        system_prompt = agent.system_prompt

        # Regra Global Absoluta: Não incluir metadados de tempo na resposta
        system_prompt += (
            "\n\n## Diretrizes de Formatação e Resposta\n"
            "1. Você verá metadados temporais no histórico de mensagens como `[CONTEXTO_TEMPORAL: ...]`. "
            "Use essas informações APENAS para cronologia interna da conversa.\n"
            "2. NUNCA inclua esses carimbos de data, horários ou quaisquer prefixos de metadados de tempo no início ou em qualquer parte de sua resposta final.\n"
            "Sua resposta deve ser natural e focada apenas no conteúdo solicitado pelo usuário.\n"
        )
        
        skills_summary = []
        greeting_config = {"initial": "", "normal": ""}

        if hasattr(agent, 'skills') and agent.skills:
            active_skills = [s for s in agent.skills if s.is_active]
            if active_skills:
                from app.schemas.skill import get_skill_capability_description, get_skills_capabilities_summary
                import re
                import json

                for skill in active_skills:
                    capabilities = get_skills_capabilities_summary(skill)
                    
                    summary_text = get_skill_capability_description(skill)
                    skills_summary.append({
                        "name": skill.name, 
                        "description": summary_text,
                        "capabilities": capabilities
                    })

                    # [GREETING CONFIG SCAN] Look for JSON with "greeting" key in skills
                    content = skill.content_md or ""
                    try:
                        json_matches = re.findall(r'```json\s*(.*?)\s*```', content, re.DOTALL)
                        for j_str in json_matches:
                            data = json.loads(j_str)
                            if isinstance(data, dict) and "greeting" in data:
                                g_data = data["greeting"]
                                if isinstance(g_data, dict):
                                    greeting_config["initial"] = g_data.get("initial", greeting_config["initial"])
                                    greeting_config["normal"] = g_data.get("normal", greeting_config["normal"])
                                    logger.info(f"[AgentFactory] 🎯 Encontrou config de saudação na skill '{skill.name}'")
                    except Exception as e:
                        logger.debug(f"[AgentFactory] Erro ao processar JSON na skill '{skill.name}': {e}")
                
                skills_instruction = """
## 🎯 Como as Skills Funcionam

Você não tem acesso às skills por padrão. Quando o usuário solicitar uma ação, 
o sistema injetará automaticamente o FLUXO DE EXECUÇÃO necessário.

Siga as etapas do fluxo NA ORDEM EXATA, sem pular. Se uma etapa tem {{ $HITL }},
você DEVE aguardar a resposta do usuário antes de continuar para a próxima etapa.
"""
                system_prompt += skills_instruction
                logger.info(f"[AgentFactory] 📌 {len(active_skills)} skill(s) disponíveis para '{agent.name}' (injetadas sob demanda)")
        
        config = {
            "id": agent_id,
            "name": agent.name,
            "description": agent.description or "",
            "system_prompt": system_prompt,
            "model": agent.model,
            "temperature": float(agent.temperature),
            "max_tokens": int(agent.max_tokens),
            "access_level": agent.access_level.value,
            "collaboration_enabled": agent.collaboration_enabled,
            "has_tools": len(tools) > 0,
            "tools": tools,
            "output_schema": agent.output_schema,  # Custom structured output schema
            "input_schema": agent.input_schema,    # Custom structured input schema
            "transition_input_schema": agent.transition_input_schema,   # System transition input
            "transition_output_schema": agent.transition_output_schema, # System transition output
            "config": agent.config or {},           # Extra config (reasoning, etc.)
            "status_updates_enabled": agent.status_updates_enabled,
            "status_updates_config": agent.status_updates_config,
            "resilience": agent.resilience_config.to_dict() if agent.resilience_config else {},
            "agent_model": agent,  # Keep reference for collaboration
            "skills_summary": skills_summary,  # For orchestrator to see collaborator skills
            "greeting_config": greeting_config,
            "provider": agent.provider if hasattr(agent, "provider") else None,
            "execution_mode": getattr(getattr(agent, "execution_mode", None), "value", "balanced"),
        }
        
        self._agent_cache[agent_id] = config
        return config
    
    def create_llm(self, agent_config: Dict[str, Any]) -> ChatOpenAI:
        """Create LLM instance for an agent, routing to the correct provider.
        Supports reasoning models (O1, O3, DeepSeek R1) with special parameters.
        Supports Qwen3 sampling parameters (top_p, top_k, min_p, etc).
        Automatically injects cost-tracking callbacks for LangSmith observability."""
        model_id = agent_config.get("model", "gpt-4o-mini")
        extra_config = agent_config.get("config", {})
        is_reasoning = extra_config.get("is_reasoning_model", False)

        # Build kwargs based on model type
        kwargs = {"model": model_id}

        if is_reasoning:
            # Reasoning models: no temperature, use reasoning_effort and max_completion_tokens
            reasoning_effort = extra_config.get("reasoning_effort", "medium")
            max_completion_tokens = extra_config.get("max_completion_tokens", 16384)

            # Qwen3 thinking models use temperature=0.6, OpenAI O1/O3 use 1.0
            if "qwen" in model_id.lower():
                kwargs["temperature"] = 0.6
            else:
                kwargs["temperature"] = 1

            kwargs["model_kwargs"] = {
                "reasoning_effort": reasoning_effort,
                "max_completion_tokens": max_completion_tokens
            }
        else:
            # Traditional models: use temperature and max_tokens
            kwargs["temperature"] = agent_config.get("temperature", 0.7)
            kwargs["max_tokens"] = agent_config.get("max_tokens", 2048)

            # Universal sampling params (supported by OpenAI and Qwen)
            universal_params = ['top_p', 'presence_penalty', 'frequency_penalty']
            for param in universal_params:
                if param in extra_config and extra_config[param] is not None:
                    kwargs[param] = extra_config[param]

            # Qwen-specific sampling params (only for Qwen models)
            if "qwen" in model_id.lower():
                qwen_params = ['top_k', 'min_p', 'repetition_penalty']
                if "model_kwargs" not in kwargs:
                    kwargs["model_kwargs"] = {}
                
                # We use extra_body to send parameters that are not part of the standard 
                # OpenAI SDK signature to avoid TypeError: unexpected keyword argument
                if "extra_body" not in kwargs["model_kwargs"]:
                    kwargs["model_kwargs"]["extra_body"] = {}
                
                for param in qwen_params:
                    if param in extra_config and extra_config[param] is not None:
                        kwargs["model_kwargs"]["extra_body"][param] = extra_config[param]

        # Structured output: force JSON if output_schema is defined
        if agent_config.get("output_schema"):
            kwargs["response_format"] = {"type": "json_object"}

        # Determina o provedor e as credenciais
        provider = agent_config.get("provider")

        if provider and provider.is_active:
            # Custom AI Provider (Ollama, Anthropic, etc.)
            kwargs["api_key"] = provider.api_key
            if provider.base_url:
                base_url = provider.base_url
                # Heurística: Se não tem /v1 e parece ser uma URL de base, adiciona /v1
                # Isso resolve o problema comum de 404 no Ollama (que exige /v1 para compatibilidade OpenAI)
                if "/v1" not in base_url and "/api" not in base_url:
                    base_url = base_url.rstrip("/") + "/v1"

                kwargs["base_url"] = base_url
                logger.info(f"[AgentFactory] 🌐 Using custom provider '{provider.name}' at '{base_url}' for model '{model_id}'")
            else:
                logger.info(f"[AgentFactory] 🌐 Using custom provider '{provider.name}' (no base_url) for model '{model_id}'")
        else:
            # Fallback para lógica padrão (OpenRouter/OpenAI)
            openrouter_specials = ["sambanova", "groq"]
            is_openrouter = "/" in model_id or model_id in openrouter_specials

            if is_openrouter:
                # OpenRouter model
                kwargs["api_key"] = settings.OPENROUTER_API_KEY
                kwargs["base_url"] = "https://openrouter.ai/api/v1"
            else:
                # OpenAI direct
                kwargs["api_key"] = settings.OPENAI_API_KEY

        # Apply resilience timeout
        resilience_cfg = agent_config.get("resilience", {})
        timeout_seconds = resilience_cfg.get("timeout_seconds")
        if timeout_seconds:
            kwargs["timeout"] = float(timeout_seconds)

        # Inject cost-tracking callbacks (only when LangSmith tracing is active)
        if settings.LANGCHAIN_TRACING_V2:
            kwargs["callbacks"] = build_cost_callbacks(
                model=model_id,
                openrouter_api_key=settings.OPENROUTER_API_KEY,
                openai_api_key=settings.OPENAI_API_KEY,
            )

        return ChatOpenAI(**kwargs)
    
    def get_run_config(self, agent_config: Dict[str, Any]) -> RunnableConfig:
        """Create LangSmith run configuration for tracing"""
        return RunnableConfig(
            run_name=f"Agent: {agent_config['name']}",
            metadata={
                "agent_id": agent_config["id"],
                "agent_name": agent_config["name"],
                "has_tools": agent_config["has_tools"],
                "model": agent_config["model"]
            },
            tags=[f"agent:{agent_config['name']}", agent_config["access_level"]]
        )
    
    async def _inject_training_rules(self, agent_config: Dict[str, Any], messages: List[Any], system_prompt: str) -> str:
        """Fetch RLHF training rules for the current agent and inject them into the system prompt."""
        if not agent_config.get("training_memory_enabled") or not messages:
            return system_prompt
            
        try:
            from langchain_core.messages import HumanMessage
            last_user_content = ""
            for msg in reversed(messages):
                if isinstance(msg, HumanMessage) and msg.content:
                    last_user_content = str(msg.content)
                    break
            
            if last_user_content:
                from app.weaviate_client import get_weaviate
                weaviate_client = get_weaviate()
                rules = await weaviate_client.search_agent_self_memories(
                    agent_id=str(agent_config["id"]),
                    query=last_user_content,
                    limit=3,
                    memory_type="training_rule"
                )
                
                if rules:
                    rules_text = "\n".join([f"- {r['content']}" for r in rules])
                    system_prompt += f"\n\n## 🧠 MODO DE TREINAMENTO (RLHF) ATIVO\nO administrador definiu as seguintes regras de comportamento baseadas em feedbacks de interações recentes similares. Siga-as RIGOROSAMENTE:\n{rules_text}\n"
                    logger.info(f"[AgentFactory] 🧠 Injetou {len(rules)} regra(s) de treinamento para '{agent_config['name']}'")
        except Exception as e:
            logger.error(f"[AgentFactory] Error fetching training memory rules: {e}")
            
        return system_prompt

    async def _get_dynamic_skills_prompt(self, agent_config: Dict[str, Any], messages: List[Any]) -> str:
        """Get dynamic skills injection prompt based on user intent."""
        from langchain_core.messages import HumanMessage
        import re
        
        last_user_content = ""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage) and msg.content:
                last_user_content = str(msg.content)
                break
                
        if not last_user_content:
            return ""
            
        # Strip temporal prefix to not confuse the router
        last_user_content = re.sub(r'\[CONTEXTO_TEMPORAL:\s*[^\]]*\]\s*', '', last_user_content).strip()
            
        agent = agent_config.get("agent_model")
        if not agent or not getattr(agent, "skills", None):
            return ""
            
        active_skills = [s for s in agent.skills if s.is_active]
        if not active_skills:
            return ""
            
        always_active_skills = [s for s in active_skills if getattr(s, "always_active", False)]
        regular_skills = [s for s in active_skills if not getattr(s, "always_active", False)]
        
        injection_text = ""
        
        try:
            from app.services.skill_detector import get_skill_content_for_capability, extract_all_flows
            
            # 1. Always Active Skills
            for skill in always_active_skills:
                all_flows = extract_all_flows(skill)
                if all_flows:
                    flows_text = "\n\n".join([
                        f"### Etapa {f['etapa']}\n{f['flow']}\n" + 
                        ("⚠️ **AGUARDE RESPOSTA DO USUÁRIO ANTES DE CONTINUAR**\n" if f['has_hitl'] else "")
                        for f in all_flows
                    ])
                    flow_injection = f"\n---\n\n## 🎯 FLUXO DE EXECUÇÃO OBRIGATÓRIO - {skill.name}\n\nSiga as etapas ABAIXO NA ORDEM EXATA, SEM PULAR ETAPAS:\n\n{flows_text}\n\n---\n"
                    injection_text += flow_injection
                    logger.info(f"[AgentFactory] 🎯 Injected always_active flow from skill '{skill.name}'")
                else:
                    from app.schemas.skill import get_skills_capabilities_summary
                    caps = get_skills_capabilities_summary(skill)
                    injected_count = 0
                    for cap in caps:
                        cap_content = get_skill_content_for_capability(skill, cap["header"])
                        if cap_content:
                            skill_injection = f"\n---\n\n## 🔹 CAPABILITY ATIVADA: {cap['header']} (Obrigatório)\n\n{cap_content}\n\n---\n"
                            injection_text += skill_injection
                            injected_count += 1
                            
                    if injected_count == 0 and skill.content_md:
                        skill_injection = f"\n---\n\n## 🔹 CAPABILITIES DA SKILL ATIVA: {skill.name}\n\n{skill.content_md}\n\n---\n"
                        injection_text += skill_injection
            
            # 2. Regular Skills via Router
            if regular_skills:
                from app.orchestrator.skill_router import SkillRouter
                router = SkillRouter()
                skill_route = await router.analyze(last_user_content, regular_skills)
                
                if skill_route:
                    skill = skill_route["skill"]
                    all_flows = extract_all_flows(skill)
                    
                    if all_flows:
                        flows_text = "\n\n".join([
                            f"### Etapa {f['etapa']}\n{f['flow']}\n" + 
                            ("⚠️ **AGUARDE RESPOSTA DO USUÁRIO ANTES DE CONTINUAR**\n" if f['has_hitl'] else "")
                            for f in all_flows
                        ])
                        
                        flow_injection = f"\n---\n\n## 🎯 FLUXO DE EXECUÇÃO DETECTADO - {skill.name}\n\nO usuário solicitou uma ação que exige este fluxo. Siga as etapas ABAIXO NA ORDEM EXATA, SEM PULAR ETAPAS:\n\n{flows_text}\n\n---\n"
                        injection_text += flow_injection
                        logger.info(f"[AgentFactory] 🎯 Injected {len(all_flows)} flow(s) from skill '{skill.name}' (via Skill Router)")
                    else:
                        capability = skill_route.get("capability")
                        if capability:
                            capability_content = get_skill_content_for_capability(skill, capability["header"])
                            if capability_content:
                                skill_injection = f"\n---\n\n## 🔹 CAPABILITY ATIVADA: {capability['header']}\n\nO usuário solicitou uma ação que exige esta capability. Siga rigorosamente as instruções:\n\n{capability_content}\n\n---\n"
                                injection_text += skill_injection
                                logger.info(f"[AgentFactory] 🎯 Injected skill capability '{capability['header']}' from skill '{skill.name}'")
        except Exception as e:
            import traceback
            logger.error(f"[AgentFactory] Failed to detect and inject skills: {e}")
            traceback.print_exc()
            
        return injection_text
    
    async def invoke_agent(
        self,
        agent_config: Dict[str, Any],
        messages: List[Any],
        rag_context: Optional[str] = None,
        context_data: Optional[Dict[str, Any]] = None,
        execution_mode_override: Optional[str] = None,
    ) -> str:
        """
        Invoke an agent with messages and return response.
        Uses ReAct if agent has tools, otherwise simple LLM call.
        """
        from app.schemas.structured_output import format_context_data_for_prompt
        
        llm = self.create_llm(agent_config)
        run_config = self.get_run_config(agent_config)

        resolved_execution_mode = (
            (execution_mode_override or "").strip().lower()
            or str(agent_config.get("execution_mode") or "balanced").strip().lower()
        )
        if resolved_execution_mode not in {"balanced", "tools_first", "orchestrator_first"}:
            resolved_execution_mode = "balanced"

        budget_cfg = (agent_config.get("config") or {}).get("execution_budget") or {}
        budget = ExecutionBudget(
            max_total_actions=int(budget_cfg.get("max_total_actions_per_turn", 7)),
            max_tool_calls=int(budget_cfg.get("max_tool_calls_per_turn", 5)),
            max_collab_calls=int(budget_cfg.get("max_collab_calls_per_turn", 2)),
            max_wall_time_seconds=int(budget_cfg.get("max_wall_time_per_turn_seconds", 35)),
        )
        seen_fingerprints = set()

        # Build system prompt
        system_prompt = agent_config["system_prompt"]
        
        # Inject context data if provided
        if context_data:
            input_schema = agent_config.get("input_schema")
            context_section = None  # Initialize before try to avoid UnboundLocalError
            
            # --- Ultra-strict filtering based on MCP metadata ---
            try:
                from app.services.mcp_tools import get_agent_mcp_metadata
                mcp_meta = await get_agent_mcp_metadata(self.db, str(agent_config["id"]))
                
                from_ai_names = mcp_meta["from_ai_names"]
                request_only_paths = mcp_meta["request_paths"] - from_ai_names
                
                # Add global safety paths that should ALMOST NEVER be seen by AI
                # unless they are explicitly marked as $fromAI (unlikely)
                global_safe_prune = {"system.apikey", "system.baseUrlBasileia", "church._id", "member.phone"}
                request_only_paths.update(global_safe_prune - from_ai_names)
                
                # 1. Enrichment: Ensure $fromAI fields are in the context prompt if they exist in source
                # Only inject if the user hasn't explicitly defined a strict input_schema
                effective_input_schema = input_schema.copy() if isinstance(input_schema, dict) else {}
                if not input_schema:
                    for name in from_ai_names:
                        if name not in effective_input_schema:
                            effective_input_schema[name] = {"type": "string", "description": "Campo dinâmico para ferramenta"}
                
                # Update input_schema reference for format_context_data_for_prompt
                input_schema = effective_input_schema

                # 2. Pruning: Identify fields that are ONLY for $request (system) and NOT for $fromAI (agent)
                # These should be HIDDEN from the agent to prevent "IA decision" leaks.
                if request_only_paths:
                    # Create a DEEP copy to avoid mutating original context_data shared across agents/turns
                    context_data_for_prompt = copy.deepcopy(context_data)
                    
                    def prune_path(data, parts):
                        if not parts or not isinstance(data, dict):
                            return
                        key = parts[0]
                        if len(parts) == 1:
                            if key in data:
                                del data[key]
                        else:
                            if key in data and isinstance(data[key], dict):
                                prune_path(data[key], parts[1:])

                    def is_path_in_schema(schema, path_str):
                        if not schema or not isinstance(schema, dict):
                            return False
                        current = schema
                        if current.get("type") == "object" and "properties" in current:
                            current = current.get("properties", {})
                        parts = path_str.split('.')
                        for part in parts:
                            if not isinstance(current, dict):
                                return False
                            if part not in current:
                                return False
                            current = current[part]
                            if isinstance(current, dict) and current.get("type") == "object" and "properties" in current:
                                current = current.get("properties", {})
                        return True
                    
                    paths_pruned_count = 0
                    for path in request_only_paths:
                        # Skip pruning if the user explicitly requested this field in their input schema
                        if not is_path_in_schema(input_schema, path):
                            prune_path(context_data_for_prompt, path.split('.'))
                            paths_pruned_count += 1
                    
                    logger.info(f"[AgentFactory] 🛡️ Pruned {paths_pruned_count} request-only field(s) from prompt context.")
                    
                    # Use the pruned copy for formatting
                    context_section = format_context_data_for_prompt(context_data_for_prompt, input_schema)
                else:
                    context_section = format_context_data_for_prompt(context_data, input_schema)
            except Exception as e:
                logger.warning(f"[AgentFactory] Failed to get MCP metadata for strict filtering: {e}")
                # Fallback: format context without pruning so the agent still works
                context_section = format_context_data_for_prompt(context_data, input_schema)
            
            if context_section:
                system_prompt += context_section
        
        # Inject HITL Sentinel Rules
        if agent_config.get("resilience"):
            res_cfg = agent_config["resilience"]
            hitl_user = res_cfg.get("hitl_user_approval_enabled", False)
            hitl_admin = res_cfg.get("hitl_admin_approval_enabled", False)
            
            if hitl_user or hitl_admin:
                hitl_msg = res_cfg.get("hitl_message_template") or ""
                system_prompt += "\n\n## 🛑 INTERVENÇÃO HUMANA OBRIGATÓRIA (HITL ATIVO)\n"
                system_prompt += "Você **DEVE** interromper sua execução e aguardar a aprovação ou resposta de um humano antes de tomar a ação final desta tarefa.\n"
                system_prompt += "Para solicitar esta aprovação, você deve formular sua pergunta para o humano e OBRIGATORIAMENTE incluir a tag `{{ $HITL }}` ao final de sua fala.\n"
                if hitl_msg:
                    system_prompt += f"Template sugerido para sua pergunta (Adapte conforme o contexto, mas mantenha o sentido da aprovação): \"{hitl_msg}\"\n"
                system_prompt += "REGRA CRÍTICA: Se a resposta do humano já foi fornecida acima no histórico (ex: você já fez a pergunta e ele acabou de responder aprovando), NÃO PARE. Vá em frente e execute a ação utilizando a tag `[FIM_DE_INTERACAO]` caso não haja mais o que fazer após a ação.\n"

        # Inject RLHF Training Rules
        system_prompt = await self._inject_training_rules(agent_config, messages, system_prompt)
        
        # Get Dynamic Skills Prompt (we will append it at the VERY END for maximum attention)
        dynamic_skills_prompt = await self._get_dynamic_skills_prompt(agent_config, messages)
        
        # Add RAG context if available
        if rag_context:
            system_prompt += f"""

## Contexto da Base de Conhecimento

Use as seguintes informações para responder:

{rag_context}

---

Cite a fonte quando usar informações do contexto acima.
"""

        # Resolve global macros like {{ $now }} before execution
        from app.utils.macros import resolve_global_macros
        system_prompt = resolve_global_macros(system_prompt, context_data)

        system_prompt += (
            "\n\n## Modo de Execução (Determinístico)\n"
            f"- Modo resolvido deste turno: {resolved_execution_mode}\n"
            "- Você deve obedecer os limites de execução e evitar chamadas redundantes.\n"
            "- Nunca repita a mesma ferramenta com os mesmos argumentos no mesmo turno.\n"
        )

        if agent_config["has_tools"]:
            tool_list = "\n".join([f"- **{t.name}**: {t.description}" for t in agent_config["tools"]])
            skills_reminder = ""
            if agent_config.get("skills_summary"):
                skill_names = [s["name"] for s in agent_config["skills_summary"]]
                skills_reminder = (
                    f"\n\n## ⚠️ LEMBRETE DE SKILLS ATIVAS\n"
                    f"Você TEM skills ativas: {', '.join(skill_names)}.\n"
                    f"Consulte e aplique RIGOROSAMENTE as instruções das skills ANTES de responder.\n"
                    f"Se uma skill define um passo-a-passo, siga-o na ORDEM EXATA.\n"
                )

            resilience_cfg = agent_config.get("resilience", {})
            max_retries = resilience_cfg.get("max_retries", 3)
            timeout_seconds = resilience_cfg.get("timeout_seconds", 120)

            if resolved_execution_mode == "tools_first":
                planner_llm = llm.with_structured_output(ToolFirstPlan)
                planner_messages = [
                    SystemMessage(content=(
                        "Gere um plano curto para usar ferramentas com prioridade. "
                        "Responda apenas no schema fornecido."
                    )),
                    HumanMessage(content=f"Solicitação atual: {messages[-1].content if messages else ''}"),
                ]
                try:
                    plan = await planner_llm.ainvoke(planner_messages, config=run_config)
                    if isinstance(plan, ToolFirstPlan):
                        budget.max_tool_calls = min(budget.max_tool_calls, int(plan.max_tool_calls))
                        budget.max_collab_calls = min(budget.max_collab_calls, int(plan.max_collab_calls))
                        logger.info(
                            "[AgentFactory] 🧭 tools_first plan=%s max_tool_calls=%s max_collab_calls=%s",
                            plan.steps,
                            budget.max_tool_calls,
                            budget.max_collab_calls,
                        )
                except Exception as planner_err:
                    logger.warning(f"[AgentFactory] planner tools_first fallback: {planner_err}")

            def _select_tools_for_mode(mode: str):
                tools = agent_config["tools"]
                if mode == "orchestrator_first":
                    return [t for t in tools if str(getattr(t, "name", "")).startswith("consultar_")] or tools
                if mode == "tools_first":
                    return [t for t in tools if not str(getattr(t, "name", "")).startswith("consultar_")] or tools
                return tools

            selected_tools = _select_tools_for_mode(resolved_execution_mode)

            # Enforce budget and anti-loop by wrapping each tool in a proxy
            # We create proper StructuredTool instances so langgraph ToolNode recognises them
            from langchain_core.tools import StructuredTool

            def _make_guarded_tool(tool, budget, seen_fps, is_collab):
                """Create a StructuredTool wrapper with budget/anti-loop enforcement."""

                async def _guarded_ainvoke(**kwargs):
                    fp = _fingerprint_tool_call(tool.name, kwargs)
                    if fp in seen_fps:
                        return "Tool call blocked: repeated same arguments in current turn."
                    if not budget.consume("collab" if is_collab else "tool"):
                        return f"Tool call blocked: {budget.stop_reason()}."
                    seen_fps.add(fp)
                    # Delegate to original tool
                    if hasattr(tool, "ainvoke"):
                        return await tool.ainvoke(kwargs)
                    elif hasattr(tool, "_arun"):
                        return await tool._arun(**kwargs)
                    elif hasattr(tool, "invoke"):
                        return tool.invoke(kwargs)
                    elif hasattr(tool, "_run"):
                        return tool._run(**kwargs)
                    else:
                        raise AttributeError(f"Tool '{tool.name}' has no invoke/_run method")

                def _guarded_invoke(**kwargs):
                    fp = _fingerprint_tool_call(tool.name, kwargs)
                    if fp in seen_fps:
                        return "Tool call blocked: repeated same arguments in current turn."
                    if not budget.consume("collab" if is_collab else "tool"):
                        return f"Tool call blocked: {budget.stop_reason()}."
                    seen_fps.add(fp)
                    if hasattr(tool, "invoke"):
                        return tool.invoke(kwargs)
                    elif hasattr(tool, "_run"):
                        return tool._run(**kwargs)
                    else:
                        raise AttributeError(f"Tool '{tool.name}' has no invoke/_run method")

                return StructuredTool(
                    name=tool.name,
                    description=getattr(tool, "description", "") or tool.name,
                    func=_guarded_invoke,
                    coroutine=_guarded_ainvoke,
                    args_schema=getattr(tool, "args_schema", None),
                )

            selected_tools = [
                _make_guarded_tool(t, budget, seen_fingerprints, t.name.startswith("consultar_"))
                for t in selected_tools
            ]

            tool_instructions = f"""
{skills_reminder}
## Árvore de Ferramentas / MCPs Disponíveis
Você tem acesso às seguintes ferramentas (MCPs). Relacione os passos solicitados nas suas skills com os nomes listados abaixo, que são os métodos reais que você pode invocar:
{tool_list}

## Instruções de Ferramentas e Resiliência (MUITO IMPORTANTE)

Você tem ferramentas locais e remotas (MCP) disponíveis. USE-AS SEMPRE que necessário para completar suas tarefas ou consultar o banco.
 REGRA CRÍTICA DE RETENTATIVA: Se a execução de uma ferramenta retornar explicitamente um campo "error" ou status de falha, você **NÃO DEVE DESISTIR** imediatamente.
- Você DEVE TENTAR EXECUTAR A FERRAMENTA NOVAMENTE, corrigindo os parâmetros com base na mensagem de erro.
- O limite máximo de tentativas para uma mesma ferramenta é de {max_retries} tentativas.
- Se uma ferramenta retornar dados válidos (lista, objeto, mensagem de sucesso), NÃO repita a chamada. Avance para o próximo passo.
- Somente se falhar definitivamente após {max_retries} tentativas, explique ao usuário o motivo da falha.
- **NUNCA chame a mesma ferramenta com os mesmos argumentos repetidamente.**
- ⏱️ LIMITE DE TEMPO: Você tem no máximo {timeout_seconds} segundos para completar toda a execução. Priorize as ações mais importantes e evite chamadas desnecessárias de ferramentas.
- ✅ REGRA DE FINALIZAÇÃO: Se você já possui informação suficiente para responder o usuário, NÃO solicite mais passos. Responda imediatamente com a resposta final, mesmo que você achasse que precisaria de mais dados.
"""
            full_prompt = system_prompt + tool_instructions
            
            # AGORA ANEXA AS SKILLS NO FIM DE TUDO!
            if dynamic_skills_prompt:
                full_prompt += f"\n\n## 🚨 DIRETRIZES DE FLUXO E SKILLS (PRIORIDADE MÁXIMA)\n{dynamic_skills_prompt}"
                
            agent_messages = [SystemMessage(content=full_prompt)] + messages

            react_agent = create_react_agent(
                model=llm,
                tools=selected_tools,
            )


            logger.info(
                "[AgentFactory] 🤖 Invocando ReAct agent='%s' model='%s' mode=%s tools=%s",
                agent_config["name"],
                agent_config["model"],
                resolved_execution_mode,
                [t.name for t in selected_tools],
            )

            recursion_limit = max(25, max_retries * 6 + 8)

            # Tratamento para erro "need more steps" do LangGraph
            from langgraph.errors import GraphRecursionError

            try:
                if resolved_execution_mode in {"tools_first", "orchestrator_first"}:
                    class ExecState(TypedDict, total=False):
                        messages: List[Any]

                    graph = StateGraph(ExecState)

                    async def run_agent_node(state: ExecState):
                        if not budget.can_continue():
                            return {"messages": [AIMessage(content=f"Execução interrompida: {budget.stop_reason()}.")]}
                        result = await react_agent.ainvoke(
                            {"messages": state["messages"]},
                            config={**run_config, "recursion_limit": recursion_limit},
                        )
                        return {"messages": result.get("messages", [])}

                    graph.add_node("run_agent", run_agent_node)
                    graph.add_edge(START, "run_agent")
                    graph.add_edge("run_agent", END)
                    compiled = graph.compile()
                    result = await compiled.ainvoke({"messages": agent_messages})
                else:
                    result = await react_agent.ainvoke(
                        {"messages": agent_messages},
                        config={**run_config, "recursion_limit": recursion_limit},
                    )
            except GraphRecursionError as recursion_err:
                logger.warning(f"[AgentFactory] ⚠️ LangGraph recursion limit atingido, extraindo última resposta válida: {recursion_err}")
                # Extraímos o estado parcial que o LangGraph retorna mesmo no erro
                if hasattr(recursion_err, 'args') and len(recursion_err.args) > 1 and 'state' in recursion_err.args[1]:
                    result = recursion_err.args[1]['state']
                    logger.info("[AgentFactory] ✅ Recuperado estado parcial do agente")
                else:
                    # Fallback: executar LLM diretamente sem ReAct
                    try:
                        logger.info("[AgentFactory] 🔄 Fallback para LLM direto sem ferramentas")
                        response = await llm.ainvoke([SystemMessage(content=full_prompt)] + messages, config=run_config)
                        return response.content
                    except Exception as fallback_err:
                        logger.error(f"[AgentFactory] ❌ Fallback também falhou: {fallback_err}")
                        return "Desculpe, não consegui processar esta solicitação completamente. Por favor, reformule sua pergunta ou tente novamente."

            final_messages = result.get("messages", [])
            for msg in final_messages:
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        logger.info(
                            "[AgentFactory] 🛠️ TOOL_CALL agent='%s' mode=%s tool=%r args=%s",
                            agent_config["name"],
                            resolved_execution_mode,
                            tc.get("name"),
                            json.dumps(tc.get("args", {}), default=str, ensure_ascii=False)[:400],
                        )
                if isinstance(msg, ToolMessage):
                    logger.info(
                        "[AgentFactory] 📨 TOOL_RESULT mode=%s tool_call_id=%r preview=%r",
                        resolved_execution_mode,
                        msg.tool_call_id,
                        str(msg.content)[:400],
                    )

            logger.info(
                "[AgentFactory] 📊 execution mode=%s actions=%s tool_calls=%s collab_calls=%s stop_reason=%s",
                resolved_execution_mode,
                budget.actions_used,
                budget.tool_calls_used,
                budget.collab_calls_used,
                budget.stop_reason(),
            )

            for msg in reversed(final_messages):
                if isinstance(msg, AIMessage) and msg.content and msg.content.strip():
                    if not (hasattr(msg, "tool_calls") and msg.tool_calls):
                        return msg.content

            for msg in reversed(final_messages):
                if isinstance(msg, AIMessage) and msg.content and msg.content.strip():
                    return msg.content

            logger.warning(f"[AgentFactory] ⚠️ No non-empty final AIMessage found for agent '{agent_config['name']}'.")
            return "Ocorreu um erro ao processar a resposta final. Por favor, tente novamente."
        
        else:
            # Simple LLM call — add skills reminder at end of prompt
            if agent_config.get("skills_summary"):
                skill_names = [s["name"] for s in agent_config["skills_summary"]]
                system_prompt += (
                    f"\n\n## ⚠️ LEMBRETE DE SKILLS ATIVAS\n"
                    f"Você TEM skills ativas: {', '.join(skill_names)}.\n"
                    f"Consulte e aplique RIGOROSAMENTE as instruções das skills ANTES de responder.\n"
                    f"Se uma skill define um passo-a-passo, siga-o na ORDEM EXATA.\n"
                )
                
            if dynamic_skills_prompt:
                system_prompt += f"\n\n## 🚨 DIRETRIZES DE FLUXO E SKILLS (PRIORIDADE MÁXIMA)\n{dynamic_skills_prompt}"

            all_messages = [SystemMessage(content=system_prompt)] + messages
            
            response = await llm.ainvoke(all_messages, config=run_config)
            return response.content
    
    def clear_cache(self):
        """Clear the agent configuration cache"""
        self._agent_cache.clear()
    
    async def invoke_agent_structured(
        self,
        agent_config: Dict[str, Any],
        messages: List[Any],
        rag_context: Optional[str] = None,
        context_data: Optional[Dict[str, Any]] = None,
        execution_mode_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Invoke an agent with structured JSON output.
        Uses the agent's output_schema if defined, otherwise uses default.
        """
        from app.schemas.structured_output import get_output_schema_for_agent, format_context_data_for_prompt
        
        llm = self.create_llm(agent_config)
        
        # Create config for structured output tracing
        run_config = RunnableConfig(
            run_name=agent_config["name"],
            metadata={
                "agent_id": agent_config["id"],
                "agent_name": agent_config["name"],
                "has_tools": agent_config.get("has_tools", False),
                "model": agent_config["model"],
                "structured": True
            },
            tags=[f"agent:{agent_config['name']}", "structured"]
        )
        
        # Get output schema
        output_schema = agent_config.get("output_schema")
        output_class = get_output_schema_for_agent(output_schema)
        
        # Create structured LLM
        structured_llm = llm.with_structured_output(output_class)
        
        # Build system prompt with structured output instructions
        system_prompt = agent_config["system_prompt"]
        
        # Inject context data if provided
        if context_data:
            input_schema = agent_config.get("input_schema")
            context_section = format_context_data_for_prompt(context_data, input_schema)
            if context_section:
                system_prompt += context_section
                
        # Inject RLHF Training Rules
        system_prompt = await self._inject_training_rules(agent_config, messages, system_prompt)
        
        # Get Dynamic Skills Prompt
        dynamic_skills_prompt = await self._get_dynamic_skills_prompt(agent_config, messages)
        
        # Add RAG context if available
        if rag_context:
            system_prompt += f"""

## Contexto da Base de Conhecimento

Use as seguintes informações para responder:

{rag_context}

---

Cite a fonte quando usar informações do contexto acima.
"""
        
        # Add structured output instruction
        schema_fields = list(output_class.model_fields.keys())
        system_prompt += f"""

## Formato de Resposta

Você DEVE responder com um objeto JSON estritamente estruturado contendo os seguintes campos EXATOS: {', '.join(schema_fields)}.
Se houver o campo 'output', ele DEVE conter sua resposta completa ao usuário, NUNCA o omita.
"""
        
        # AGORA ANEXA AS SKILLS NO FIM DE TUDO!
        if dynamic_skills_prompt:
            system_prompt += f"\n\n## 🚨 DIRETRIZES DE FLUXO E SKILLS (PRIORIDADE MÁXIMA)\n{dynamic_skills_prompt}"
            
        all_messages = [SystemMessage(content=system_prompt)] + messages
        
        try:
            result = await structured_llm.ainvoke(all_messages, config=run_config)
            return result.model_dump()
        except Exception as e:
            logger.error(f"[AgentFactory] ❌ Structured output error em '{agent_config['name']}': {e}", exc_info=True)
            
            # Tentar salvar campos parciais do erro de validação (comum em novos modelos do OpenRouter)
            if "ValidationError" in str(type(e)):
                try:
                    for err in getattr(e, "errors", lambda: [])():
                        if "input_value" in err and isinstance(err["input_value"], dict):
                            partial_data = err["input_value"]
                            logger.warning(f"[AgentFactory] ⚠️ Resgatando dados parciais do LLM: {partial_data}")
                            
                            # Garantir que todos os campos existam para não quebrar a tipagem
                            for field_name in output_class.model_fields.keys():
                                if field_name not in partial_data:
                                    partial_data[field_name] = ""
                                    
                            # Se 'output' ficou vazio, solicitamos apenas a resposta textual num invoke regular
                            if "output" in partial_data and not partial_data["output"]:
                                logger.warning("[AgentFactory] ⚠️ Campo 'output' omitido, fazendo fallback textual...")
                                fallback_text = await self.invoke_agent(
                                    agent_config,
                                    messages,
                                    rag_context,
                                    context_data,
                                    execution_mode_override=execution_mode_override,
                                )
                                partial_data["output"] = fallback_text
                                
                            return partial_data
                except Exception as inner_e:
                    logger.error(f"[AgentFactory] ❌ Falha ao recuperar JSON parcial: {inner_e}")
            
            # Fallback final se falhar e não recuperar JSON parcial
            regular_response = await self.invoke_agent(
                agent_config,
                messages,
                rag_context,
                context_data,
                execution_mode_override=execution_mode_override,
            )
            return {"output": regular_response}

