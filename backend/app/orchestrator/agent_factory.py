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


def _clean_and_trim_messages(
    messages: List[Any],
    max_history: int = 8,
    for_tools: bool = True,
) -> List[Any]:
    """
    Cleans conversation messages for LLM consumption:
    - Strips standalone ToolMessages that are not paired in history
    - Converts AIMessages with tool_calls to clean AIMessages (preserving content if present)
    - Trims history to the most recent `max_history` items
    - When tools/function calling are enabled (for_tools=True), strips any trailing AIMessages
      from the end of the history. This is strictly required by providers like DeepSeek (OpenRouter)
      which reject requests where tools are enabled and the final message is an assistant prefix/prefill:
      'Function call should not be used with prefix'.
    """
    from langchain_core.messages import ToolMessage, AIMessage

    cleaned = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            continue
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            if msg.content:
                cleaned.append(AIMessage(content=msg.content))
            continue
        cleaned.append(msg)

    trimmed = cleaned[-max_history:] if len(cleaned) > max_history else list(cleaned)

    if for_tools:
        # Strip trailing assistant messages to avoid prefix/prefill conflict with function calling
        while trimmed and isinstance(trimmed[-1], AIMessage):
            trimmed.pop()

    return trimmed


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
                selectinload(Agent.graph),
                selectinload(Agent.graph_tools),
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
                selectinload(Agent.graph),
                selectinload(Agent.graph_tools),
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
            logger.info(f"[AgentFactory] 🔍 DEBUG get_tools_for_agent context_data keys for '{agent.name}': {list(context_data.keys()) if context_data else 'None'}")
            tools = await get_tools_for_agent(self.db, agent_id, context_data)
            
            # Load Graph Tools attached to this agent
            if hasattr(agent, 'graph_tools') and agent.graph_tools:
                try:
                    from app.services.agent_graph_compiler import build_graph_tool
                    for gt in agent.graph_tools:
                        if getattr(gt, 'is_active', True):
                            g_tool = build_graph_tool(gt, self.db, context_data=context_data)
                            tools.append(g_tool)
                            logger.info(f"[AgentFactory] 🧩 Carregou Grafo como Ferramenta '{g_tool.name}' para '{agent.name}'")
                except Exception as e:
                    logger.error(f"[AgentFactory] ❌ Erro ao carregar graph_tools para '{agent.name}': {e}")

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
        
        # Injeção de Exemplos Few-Shot se ativado no agent.config
        agent_extra_config = agent.config or {}
        fs_config = agent_extra_config.get("few_shot_config", {})
        fs_examples = agent_extra_config.get("few_shot_examples", [])

        if fs_config.get("enabled") and fs_examples:
            try:
                from langchain_core.prompts import PromptTemplate, FewShotPromptTemplate

                valid_examples = []
                example_fields = set()
                for ex in fs_examples:
                    if isinstance(ex, dict) and any(str(v).strip() for v in ex.values()):
                        clean_ex = {k: str(v).strip() for k, v in ex.items() if str(v).strip()}
                        valid_examples.append(clean_ex)
                        example_fields.update(clean_ex.keys())

                if valid_examples:
                    template_parts = []
                    if "input" in example_fields:
                        template_parts.append("Entrada: {input}")
                    if "collaborator_name" in example_fields:
                        template_parts.append("Colaborador Alvo: {collaborator_name}")
                    if "acao" in example_fields:
                        template_parts.append("Ação/Direcionamento: {acao}")
                    if "output" in example_fields:
                        template_parts.append("Saída Esperada: {output}")

                    example_template = "\n".join(template_parts)
                    example_prompt = PromptTemplate(
                        input_variables=list(example_fields),
                        template=example_template
                    )

                    prefix = fs_config.get("prefix") or "Observe os seguintes exemplos de comportamento esperado:"
                    suffix = fs_config.get("suffix") or "Siga o mesmo padrão de raciocínio, uso de ferramentas e formato de resposta."

                    few_shot_prompt_obj = FewShotPromptTemplate(
                        examples=valid_examples,
                        example_prompt=example_prompt,
                        prefix=prefix,
                        suffix=suffix,
                        example_separator="\n---\n"
                    )

                    few_shot_text = few_shot_prompt_obj.format()
                    system_prompt += f"\n\n## 💡 Exemplos de Comportamento (Few-Shot Prompting)\n{few_shot_text}\n"
                    logger.info(f"[AgentFactory] 💡 Injetados {len(valid_examples)} exemplo(s) Few-Shot no system_prompt de '{agent.name}'")
            except Exception as e:
                logger.error(f"[AgentFactory] ❌ Erro ao formatar FewShotPromptTemplate para '{agent.name}': {e}", exc_info=True)

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
            "swarm_mode": getattr(agent, "swarm_mode", False),
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
            "execution_type": getattr(agent, "execution_type", "standard") or "standard",
            "graph_id": str(agent.graph_id) if getattr(agent, "graph_id", None) else None,
            "graph": getattr(agent, "graph", None),
            "bypass_llm": getattr(agent, "bypass_llm", False),
        }
        
        self._agent_cache[agent_id] = config
        return config
    
    def create_llm(self, agent_config: Dict[str, Any], session_id: Optional[str] = None) -> Any:
        """Create LLM instance for an agent, routing to the correct provider.
        Supports reasoning models (O1, O3, DeepSeek R1) with special parameters.
        Supports Qwen3 sampling parameters (top_p, top_k, min_p, etc).
        Automatically injects cost-tracking callbacks for LangSmith observability."""
        model_id = agent_config.get("model", "gpt-4o-mini") or "gpt-4o-mini"
        extra_config = agent_config.get("config", {}) or {}
        model_id_lower = model_id.lower()
        
        is_deepseek = "deepseek" in model_id_lower
        is_deepseek_reasoner = is_deepseek and ("reasoner" in model_id_lower or "r1" in model_id_lower)
        is_reasoning_active = extra_config.get("is_reasoning_model", False) or is_deepseek_reasoner
        is_openai_reasoning = (
            (is_reasoning_active or "o1" in model_id_lower or "o3" in model_id_lower or "reasoning" in model_id_lower)
            and not is_deepseek
        )

        # Build kwargs based on model type
        kwargs = {"model": model_id}

        if is_deepseek and is_reasoning_active:
            # DeepSeek V4 Pro / Flash (or R1) with reasoning/thinking enabled
            reasoning_effort = extra_config.get("reasoning_effort", "high")
            max_completion_tokens = extra_config.get("max_completion_tokens", 16384)

            kwargs["reasoning_effort"] = reasoning_effort
            kwargs["max_tokens"] = int(max_completion_tokens)
            kwargs["max_completion_tokens"] = int(max_completion_tokens)
            
            # DeepSeek V4 supports enabling thinking mode via extra_body
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

        elif is_openai_reasoning:
            # OpenAI Reasoning models (o1, o3-mini): no temperature adjustment, use reasoning_effort and max_completion_tokens
            reasoning_effort = extra_config.get("reasoning_effort", "medium")
            max_completion_tokens = extra_config.get("max_completion_tokens", 16384)

            kwargs["temperature"] = 1
            kwargs["reasoning_effort"] = reasoning_effort
            kwargs["max_tokens"] = int(max_completion_tokens)
            kwargs["max_completion_tokens"] = int(max_completion_tokens)

        else:
            # Traditional models and DeepSeek-Chat / DeepSeek-V4 non-thinking: use temperature and max_tokens
            kwargs["temperature"] = float(agent_config.get("temperature", 0.7))
            kwargs["max_tokens"] = int(agent_config.get("max_tokens", 2048))

            # Universal sampling params (supported by OpenAI, DeepSeek, and Qwen)
            universal_params = ['top_p', 'presence_penalty', 'frequency_penalty']
            for param in universal_params:
                if param in extra_config and extra_config[param] is not None:
                    kwargs[param] = extra_config[param]

            # Qwen-specific sampling params (only for Qwen models)
            if "qwen" in model_id_lower:
                qwen_params = ['top_k', 'min_p', 'repetition_penalty']
                if "extra_body" not in kwargs:
                    kwargs["extra_body"] = {}
                
                for param in qwen_params:
                    if param in extra_config and extra_config[param] is not None:
                        kwargs["extra_body"][param] = extra_config[param]

        # Structured output: force JSON if output_schema is defined
        if agent_config.get("output_schema"):
            kwargs["response_format"] = {"type": "json_object"}

        # Determina o provedor e as credenciais
        provider = agent_config.get("provider")
        
        # 1. Checar se é Google Gemini (nativamente, com ou sem provider configurado)
        is_google = False
        if provider == "google":
            is_google = True
        elif provider and hasattr(provider, "is_active") and provider.is_active:
            if hasattr(provider, "base_url") and provider.base_url and "generativelanguage.googleapis" in provider.base_url:
                is_google = True
            elif hasattr(provider, "name") and provider.name and ("gemini" in provider.name.lower() or "google" in provider.name.lower()):
                is_google = True
        elif "gemini" in model_id.lower() and "/" not in model_id and settings.GOOGLE_API_KEY:
            # Fallback dinâmico: se o nome do modelo tem gemini (e NÃO tem '/' que indica OpenRouter)
            is_google = True

        if is_google:
            from app.services.gemini_cache_service import CachedChatGoogleGenerativeAI
            
            # Pega a API key do provider ou das variáveis de ambiente
            google_api_key = provider.api_key if provider and hasattr(provider, "is_active") and provider.is_active else settings.GOOGLE_API_KEY
            logger.info(f"[AgentFactory] 🌐 Using native Google Generative AI for model '{model_id}'")
            
            # Check for cached model id override (used internally by caching service)
            if "gemini_cache_id" in extra_config and extra_config["gemini_cache_id"]:
                model_id = extra_config["gemini_cache_id"]
                logger.info(f"[AgentFactory] ⚡ Using cached model ID: {model_id}")
            
            # Instantiate Cached wrapper
            llm_google = CachedChatGoogleGenerativeAI(
                model=model_id,
                api_key=google_api_key,
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 2048)
            )
            llm_google._gemini_session_id = session_id
            llm_google._gemini_agent_id = str(agent_config.get("id", ""))
            return llm_google

        # 2. Lógica para Custom Providers (do banco de dados)
        if provider and hasattr(provider, "is_active") and provider.is_active:
            # Custom AI Provider (DeepSeek, Ollama, Anthropic, etc.)
            kwargs["api_key"] = getattr(provider, "api_key", "")
            if hasattr(provider, "base_url") and provider.base_url:
                base_url = provider.base_url.strip()
                from urllib.parse import urlparse
                parsed_url = urlparse(base_url)
                if not parsed_url.path or parsed_url.path in ("", "/"):
                    base_url = base_url.rstrip("/") + "/v1"

                kwargs["base_url"] = base_url
                logger.info(f"[AgentFactory] 🌐 Using custom provider '{provider.name}' at '{base_url}' for model '{model_id}'")
            else:
                logger.info(f"[AgentFactory] 🌐 Using custom provider '{getattr(provider, 'name', '')}' (no base_url) for model '{model_id}'")
        
        # 3. Provedor Nativo DeepSeek (via .env ou fallback por nome de modelo)
        elif provider == "deepseek" or ("deepseek" in model_id_lower and "/" not in model_id):
            kwargs["api_key"] = settings.DEEPSEEK_API_KEY
            kwargs["base_url"] = "https://api.deepseek.com/v1"
            logger.info(f"[AgentFactory] 🌐 Using native DeepSeek provider at 'https://api.deepseek.com/v1' for model '{model_id}'")

        else:
            # 4. Fallback para OpenRouter / OpenAI
            openrouter_specials = ["sambanova", "groq"]
            is_openrouter = provider == "openrouter" or "/" in model_id or model_id in openrouter_specials

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
    
    def get_run_config(self, agent_config: Dict[str, Any], context_data: Optional[Dict[str, Any]] = None) -> RunnableConfig:
        """Create LangSmith/Langfuse run configuration for tracing"""
        from app.config import get_langfuse_callback
        
        user_phone = None
        sess_id = None
        langfuse_tags = []

        if context_data:
            user_phone = context_data.get("member", {}).get("phone")
            sess_id = context_data.get("session_id")
            instancia_id = context_data.get("global", {}).get("instancia")
            church_id = context_data.get("church", {}).get("_id")

            if instancia_id:
                langfuse_tags.append(f"instancia:{instancia_id}")
            if church_id:
                langfuse_tags.append(f"church:{church_id}")
        
        callbacks = []
        langfuse_cb = get_langfuse_callback()
        if langfuse_cb:
            callbacks.append(langfuse_cb)
            
        metadata = {
            "agent_id": agent_config["id"],
            "agent_name": agent_config["name"],
            "has_tools": agent_config["has_tools"],
            "model": agent_config["model"]
        }
        
        if user_phone: metadata["langfuse_user_id"] = user_phone
        if sess_id: metadata["langfuse_session_id"] = sess_id
        if langfuse_tags: metadata["langfuse_tags"] = langfuse_tags
            
        return RunnableConfig(
            run_name=f"Agent: {agent_config['name']}",
            metadata=metadata,
            tags=[f"agent:{agent_config['name']}", agent_config["access_level"]],
            callbacks=callbacks if callbacks else None
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
    
    async def _prepare_agent_run(
        self,
        agent_config: Dict[str, Any],
        messages: List[Any],
        rag_context: Optional[str] = None,
        context_data: Optional[Dict[str, Any]] = None,
        execution_mode_override: Optional[str] = None,
    ):
        """Prepare LLM, tools, prompt and graph for agent execution."""
        from app.schemas.structured_output import format_context_data_for_prompt
        from app.utils.macros import resolve_global_macros
        from langgraph.graph import StateGraph, START, END
        from langgraph.graph.message import add_messages
        from langgraph.prebuilt import ToolNode
        from langchain_core.tools import StructuredTool
        from typing import Annotated, Sequence

        session_id = context_data.get("session_id") if context_data else None
        llm = self.create_llm(agent_config, session_id=session_id)
        run_config = self.get_run_config(agent_config, context_data)

        resolved_execution_mode = (
            (execution_mode_override or "").strip().lower()
            or str(agent_config.get("execution_mode") or "balanced").strip().lower()
        )
        if resolved_execution_mode not in {"balanced", "tools_first", "orchestrator_first"}:
            resolved_execution_mode = "balanced"

        agent_extra_config = agent_config.get("config") or {}
        budget_cfg = agent_extra_config.get("execution_budget") or {}
        allow_specialist_switching = agent_extra_config.get("allow_specialist_switching", False)

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
            context_section = None
            
            try:
                from app.services.mcp_tools import get_agent_mcp_metadata
                mcp_meta = await get_agent_mcp_metadata(self.db, str(agent_config["id"]))
                
                from_ai_names = mcp_meta["from_ai_names"]
                request_only_paths = mcp_meta["request_paths"] - from_ai_names
                global_safe_prune = {"system.apikey", "system.baseUrlBasileia", "church._id", "member.phone"}
                request_only_paths.update(global_safe_prune - from_ai_names)
                
                effective_input_schema = input_schema.copy() if isinstance(input_schema, dict) else {}
                if not input_schema:
                    for name in from_ai_names:
                        if name not in effective_input_schema:
                            effective_input_schema[name] = {"type": "string", "description": "Campo dinâmico para ferramenta"}
                
                input_schema = effective_input_schema

                if request_only_paths:
                    context_data_for_prompt = copy.deepcopy(context_data)
                    
                    def prune_path(data, parts):
                        if not parts or not isinstance(data, dict): return
                        key = parts[0]
                        if len(parts) == 1:
                            if key in data: del data[key]
                        else:
                            if key in data and isinstance(data[key], dict): prune_path(data[key], parts[1:])

                    def is_path_in_schema(schema, path_str):
                        if not schema or not isinstance(schema, dict): return False
                        current = schema
                        if current.get("type") == "object" and "properties" in current:
                            current = current.get("properties", {})
                        parts = path_str.split('.')
                        for part in parts:
                            if not isinstance(current, dict): return False
                            if part not in current: return False
                            current = current[part]
                            if isinstance(current, dict) and current.get("type") == "object" and "properties" in current:
                                current = current.get("properties", {})
                        return True
                    
                    for path in request_only_paths:
                        if not is_path_in_schema(input_schema, path):
                            prune_path(context_data_for_prompt, path.split('.'))
                    
                    context_section = format_context_data_for_prompt(context_data_for_prompt, input_schema)
                else:
                    context_section = format_context_data_for_prompt(context_data, input_schema)
            except Exception as e:
                logger.warning(f"[AgentFactory] Failed to get MCP metadata for strict filtering: {e}")
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
                    system_prompt += f"Template sugerido para sua pergunta: \"{hitl_msg}\"\n"
                system_prompt += "REGRA CRÍTICA: Se a resposta do humano já foi fornecida acima no histórico, NÃO PARE. Vá em frente.\n"

        system_prompt = await self._inject_training_rules(agent_config, messages, system_prompt)
        dynamic_skills_prompt = await self._get_dynamic_skills_prompt(agent_config, messages)
        
        if rag_context:
            system_prompt += f"\n\n## Contexto da Base de Conhecimento\n\nUse as seguintes informações para responder:\n\n{rag_context}\n\n---\n\nCite a fonte quando usar informações do contexto acima.\n"

        system_prompt = resolve_global_macros(system_prompt, context_data)
        system_prompt += f"\n\n## Modo de Execução (Determinístico)\n- Modo resolvido deste turno: {resolved_execution_mode}\n- Você deve obedecer os limites de execução.\n"

        if not agent_config["has_tools"]:
            if agent_config.get("skills_summary"):
                skill_names = [s["name"] for s in agent_config["skills_summary"]]
                system_prompt += f"\n\n## ⚠️ LEMBRETE DE SKILLS ATIVAS\nVocê TEM skills ativas: {', '.join(skill_names)}.\n"
            if dynamic_skills_prompt:
                system_prompt += f"\n\n## 🚨 DIRETRIZES DE FLUXO E SKILLS (PRIORIDADE MÁXIMA)\n{dynamic_skills_prompt}"
            
            trimmed_nr_messages = _clean_and_trim_messages(messages, max_history=8, for_tools=False)
            return {
                "is_react": False,
                "llm": llm,
                "run_config": run_config,
                "full_prompt": system_prompt,
                "messages": messages,
                "agent_messages": [SystemMessage(content=system_prompt)] + trimmed_nr_messages
            }

        tool_list = "\n".join([f"- **{t.name}**: {t.description}" for t in agent_config["tools"]])
        skills_reminder = ""
        if agent_config.get("skills_summary"):
            skill_names = [s["name"] for s in agent_config["skills_summary"]]
            skills_reminder = f"\n\n## ⚠️ LEMBRETE DE SKILLS ATIVAS\nVocê TEM skills ativas: {', '.join(skill_names)}.\n"

        resilience_cfg = agent_config.get("resilience", {})
        max_retries = resilience_cfg.get("max_retries", 3)
        timeout_seconds = resilience_cfg.get("timeout_seconds", 120)

        if resolved_execution_mode == "tools_first":
            planner_llm = llm.with_structured_output(ToolFirstPlan)
            planner_messages = [
                SystemMessage(content="Gere um plano curto para usar ferramentas com prioridade. Responda apenas no schema fornecido."),
                HumanMessage(content=f"Solicitação atual: {messages[-1].content if messages else ''}"),
            ]
            try:
                plan = await planner_llm.ainvoke(planner_messages, config=run_config)
                if isinstance(plan, ToolFirstPlan):
                    budget.max_tool_calls = min(budget.max_tool_calls, int(plan.max_tool_calls))
                    budget.max_collab_calls = min(budget.max_collab_calls, int(plan.max_collab_calls))
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
        locks = {"selected_agent": None, "tool_called": False, "collab_called": False}
        always_start_queue = agent_config.get("always_start_tools", [])
        always_end_queue = agent_config.get("always_end_tools", [])

        def is_mandatory_tool(name: str) -> bool:
            return name in always_start_queue or name in always_end_queue

        def _make_guarded_tool(tool, budget, seen_fps, is_collab):
            async def _guarded_ainvoke(**kwargs):
                if is_collab:
                    detected_agent = tool.name
                    if not is_mandatory_tool(detected_agent) and not allow_specialist_switching:
                        if locks["selected_agent"] is None: locks["selected_agent"] = detected_agent
                        elif locks["selected_agent"] != detected_agent: return f"Erro: Troca de especialista não permitida."
                    locks["collab_called"] = True
                if not is_mandatory_tool(tool.name): locks["tool_called"] = True
                fp = _fingerprint_tool_call(tool.name, kwargs)
                if fp in seen_fps: return "Tool call blocked: repeated same arguments."
                if not budget.consume("collab" if is_collab else "tool"): return f"Tool call blocked: {budget.stop_reason()}."
                seen_fps.add(fp)
                if hasattr(tool, "ainvoke"): return await tool.ainvoke(kwargs)
                elif hasattr(tool, "_arun"): return await tool._arun(**kwargs)
                elif hasattr(tool, "invoke"): return tool.invoke(kwargs)
                elif hasattr(tool, "_run"): return tool._run(**kwargs)
                else: raise AttributeError(f"Tool '{tool.name}' has no invoke/_run method")

            def _guarded_invoke(**kwargs):
                if is_collab:
                    detected_agent = tool.name
                    if not is_mandatory_tool(detected_agent) and not allow_specialist_switching:
                        if locks["selected_agent"] is None: locks["selected_agent"] = detected_agent
                        elif locks["selected_agent"] != detected_agent: return f"Erro: Troca de especialista não permitida."
                    locks["collab_called"] = True
                if not is_mandatory_tool(tool.name): locks["tool_called"] = True
                fp = _fingerprint_tool_call(tool.name, kwargs)
                if fp in seen_fps: return "Tool call blocked: repeated same arguments."
                if not budget.consume("collab" if is_collab else "tool"): return f"Tool call blocked: {budget.stop_reason()}."
                seen_fps.add(fp)
                if hasattr(tool, "invoke"): return tool.invoke(kwargs)
                elif hasattr(tool, "_run"): return tool._run(**kwargs)
                else: raise AttributeError(f"Tool '{tool.name}' has no invoke/_run method")

            return StructuredTool(
                name=tool.name,
                description=getattr(tool, "description", "") or tool.name,
                func=_guarded_invoke,
                coroutine=_guarded_ainvoke,
                args_schema=getattr(tool, "args_schema", None),
            )

        selected_tools = [_make_guarded_tool(t, budget, seen_fingerprints, t.name.startswith("consultar_")) for t in selected_tools]
        tool_instructions = f"\n{skills_reminder}\n## Árvore de Ferramentas / MCPs Disponíveis\n{tool_list}\n\n## Instruções de Ferramentas\nUSE-AS SEMPRE que necessário. Max {max_retries} retries por ferramenta.\n"
        full_prompt = system_prompt + tool_instructions
        if dynamic_skills_prompt:
            full_prompt += f"\n\n## 🚨 DIRETRIZES DE FLUXO E SKILLS (PRIORIDADE MÁXIMA)\n{dynamic_skills_prompt}"
            
        trimmed_messages = _clean_and_trim_messages(messages, max_history=8, for_tools=True)
        agent_messages = [SystemMessage(content=full_prompt)] + trimmed_messages
        llm_with_tools = llm.bind_tools(selected_tools)
        tool_node = ToolNode(selected_tools)

        class AgentExecState(TypedDict, total=False):
            messages: Annotated[Sequence[Any], add_messages]

        def _get_called_tool_names(state: AgentExecState) -> set:
            called = set()
            for msg in state["messages"]:
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        called.add(tc["name"])
            return called

        async def call_model_node(state: AgentExecState):
            if not budget.can_continue():
                return {"messages": [AIMessage(content=f"Execução interrompida: {budget.stop_reason()}.")]}
            called_tools = _get_called_tool_names(state)
            for t_name in always_start_queue:
                if t_name not in called_tools:
                    forced_tool_obj = next((t for t in selected_tools if t.name == t_name), None)
                    if forced_tool_obj:
                        llm_forced = llm.bind_tools([forced_tool_obj])
                        force_msg = HumanMessage(content=f"[SISTEMA] VOCÊ DEVE OBRIGATORIAMENTE CHAMAR A FERRAMENTA '{t_name}' AGORA MESMO.")
                        msgs_to_send = list(state["messages"])
                        while len(msgs_to_send) > 1 and isinstance(msgs_to_send[-1], AIMessage):
                            msgs_to_send.pop()
                        response = await llm_forced.ainvoke(msgs_to_send + [force_msg], config=run_config)
                        return {"messages": [response]}
            
            msgs_to_send = list(state["messages"])
            while len(msgs_to_send) > 1 and isinstance(msgs_to_send[-1], AIMessage):
                msgs_to_send.pop()
            response = await llm_with_tools.ainvoke(msgs_to_send, config=run_config)
            return {"messages": [response]}

        def should_continue_edge(state: AgentExecState) -> str:
            if agent_config.get("__direct_payload_result"):
                return END
            last_msg = state["messages"][-1]
            if not getattr(last_msg, "tool_calls", None):
                called_tools = _get_called_tool_names(state)
                for t_name in always_end_queue:
                    if t_name not in called_tools: return "force_end"
                return END
            # Se houver chamadas para colaboradores, roteamos para o nó do respectivo colaborador.
            for tc in last_msg.tool_calls:
                for t_name, c_node_name in collab_node_names:
                    if tc["name"] == t_name:
                        logger.info(f"[AgentFactory] 🔀 Routing to Sub-graph Node: {c_node_name}")
                        return c_node_name
            return "tools"

        async def force_end_node(state: AgentExecState):
            called_tools = _get_called_tool_names(state)
            for t_name in always_end_queue:
                if t_name not in called_tools:
                    forced_tool_obj = next((t for t in selected_tools if t.name == t_name), None)
                    if forced_tool_obj:
                        llm_forced = llm.bind_tools([forced_tool_obj])
                        force_msg = HumanMessage(content=f"[SISTEMA] VOCÊ DEVE OBRIGATORIAMENTE CHAMAR A FERRAMENTA '{t_name}' AGORA PARA FINALIZAR.")
                        msgs_to_send = list(state["messages"])
                        while len(msgs_to_send) > 1 and isinstance(msgs_to_send[-1], AIMessage):
                            msgs_to_send.pop()
                        response = await llm_forced.ainvoke(msgs_to_send + [force_msg], config=run_config)
                        return {"messages": [response]}
            return {"messages": []}



        agent_graph = StateGraph(AgentExecState)
        agent_graph.add_node("agent", call_model_node)
        agent_graph.add_node("tools", tool_node)
        agent_graph.add_node("force_end", force_end_node)

        # --- DYNAMIC COLLABORATOR NODES (SUB-GRAPHS) ---
        collaborators_list = agent_config.get("collaborators_list", [])
        collab_node_names = []

        def make_collab_node(collab_agent, c_name):
            async def _collab_node(state: AgentExecState):
                last_msg = state["messages"][-1]
                tc = next((t for t in getattr(last_msg, "tool_calls", []) if t["name"] == c_name), None)
                if not tc:
                    return {"messages": []}

                instrucao = tc["args"].get("instrucao", "")

                # Budget enforcement — o guard da tool não roda porque o intercept
                # desvia a chamada antes do ToolNode.
                if not budget.consume("collab"):
                    return {"messages": [ToolMessage(
                        content=f"Erro: {budget.stop_reason()}. Limite de consultas a especialistas atingido. Sintetize a resposta com os dados que já possui.",
                        tool_call_id=tc["id"],
                        name=tc["name"],
                    )]}

                from app.services.collaborator_executor import CollaboratorExecutor
                executor = CollaboratorExecutor(db=self.db)

                try:
                    logger.info(f"[AgentFactory] 🚀 Executing Sub-graph Node for '{collab_agent.name}'")
                    name, response = await executor.invoke(
                        collaborator=collab_agent,
                        instruction=instrucao,
                        session_id=context_data.get("session_id") if context_data else None,
                        context_data=context_data,
                        response_style=getattr(collab_agent, "response_style", "structured"),
                    )
                except Exception as e:
                    logger.error(f"[AgentFactory] ❌ Error in collab node '{collab_agent.name}': {e}")
                    response = f"Erro ao consultar agente {collab_agent.name}: {str(e)}"

                # Intercept direct payload in the collaborator's final response
                if response and isinstance(response, str) and '"__direct_payload"' in response:
                    import json as _dp_json
                    try:
                        parsed = _dp_json.loads(response)
                        if isinstance(parsed, dict) and parsed.get("__direct_payload"):
                            logger.info(f"[AgentFactory] ⚡ Direct payload response from collaborator '{collab_agent.name}' intercepted")
                            agent_config["__direct_payload_result"] = parsed
                    except Exception:
                        pass

                return {"messages": [ToolMessage(content=response, tool_call_id=tc["id"], name=tc["name"])]}
            return _collab_node

        import re as _re
        for collab in collaborators_list:
            safe_name = _re.sub(r'[^a-zA-Z0-9_]', '_', collab.name or "agent")
            safe_name = _re.sub(r'^[^a-zA-Z_]', '_', safe_name)
            safe_name = _re.sub(r'_+', '_', safe_name).strip('_')[:64]
            t_name = f"consultar_{safe_name}"
            c_node_name = f"collab_{safe_name}"
            collab_node_names.append((t_name, c_node_name))

            agent_graph.add_node(c_node_name, make_collab_node(collab, t_name))
            agent_graph.add_edge(c_node_name, "agent")

        agent_graph.add_edge(START, "agent")

        valid_destinations = ["tools", "force_end", END] + [c[1] for c in collab_node_names]
        agent_graph.add_conditional_edges("agent", should_continue_edge, valid_destinations)

        def route_after_tools(state: AgentExecState) -> str:
            """Se a última tool executada for do tipo always_end_queue, encerra o orquestrador imediatamente."""
            for msg in reversed(state["messages"]):
                if getattr(msg, "type", "") != "tool":
                    break
                if getattr(msg, "name", None) in always_end_queue:
                    logger.info(f"[AgentFactory] 🏁 Tool de saída final '{msg.name}' concluída. Encerrando o orquestrador.")
                    return END
            return "agent"

        agent_graph.add_conditional_edges("tools", route_after_tools, ["agent", END])
        agent_graph.add_edge("force_end", "tools")

        return {
            "is_react": True,
            "graph": agent_graph.compile(),
            "agent_messages": agent_messages,
            "run_config": run_config,
            "max_retries": max_retries,
            "full_prompt": full_prompt,
            "llm": llm,
            "budget": budget,
            "resolved_execution_mode": resolved_execution_mode,
            "name": agent_config["name"]
        }

    async def invoke_agent(
        self,
        agent_config: Dict[str, Any],
        messages: List[Any],
        rag_context: Optional[str] = None,
        context_data: Optional[Dict[str, Any]] = None,
        execution_mode_override: Optional[str] = None,
    ) -> str:
        """Invoke an agent with messages and return response."""
        # ── Graph Execution Mode (Orchestrated Agent Graph) ───────────────────
        if agent_config.get("execution_type") == "graph" and agent_config.get("graph_id"):
            try:
                from app.services.agent_graph_compiler import AgentGraphCompiler
                from app.models.agent_graph import AgentGraph
                from uuid import UUID
                graph_id = UUID(str(agent_config["graph_id"]))
                result = await self.db.execute(select(AgentGraph).where(AgentGraph.id == graph_id, AgentGraph.is_active == True))
                graph_obj = result.scalar_one_or_none()
                if graph_obj:
                    user_msg = ""
                    for m in reversed(messages):
                        if isinstance(m, HumanMessage) or (isinstance(m, dict) and m.get("role") == "user"):
                            user_msg = m.content if isinstance(m, HumanMessage) else m.get("content", "")
                            if user_msg:
                                break
                    session_id = context_data.get("session_id") if context_data else None
                    compiler = AgentGraphCompiler(self.db)
                    exec_res = await compiler.execute_graph(
                        graph=graph_obj,
                        message=user_msg or "Iniciar atendimento",
                        context_data=context_data,
                        session_id=session_id
                    )
                    logger.info(f"[AgentFactory] 🕸️ Agente '{agent_config['name']}' executado via Grafo '{graph_obj.name}' (status: {exec_res.status})")
                    return exec_res.final_output
            except Exception as e:
                logger.error(f"[AgentFactory] ❌ Erro ao executar agente '{agent_config.get('name')}' em modo grafo: {e}", exc_info=True)

        prep = await self._prepare_agent_run(agent_config, messages, rag_context, context_data, execution_mode_override)
        
        if not prep["is_react"]:
            response = await prep["llm"].ainvoke(prep["agent_messages"], config=prep["run_config"])
            return response.content

        from langgraph.errors import GraphRecursionError
        from app.orchestrator.verifier_graph import run_verifier, MAX_VERIFICATION_ATTEMPTS

        # Extract user message for semantic verification
        original_user_msg = ""
        for m in reversed(messages):
            if isinstance(m, HumanMessage) or (isinstance(m, dict) and m.get("role") == "user"):
                original_user_msg = m.content if isinstance(m, HumanMessage) else m.get("content", "")
                if original_user_msg:
                    break

        verification_attempt = 0
        current_agent_messages = list(prep["agent_messages"])
        response_text = "Ocorreu um erro ao processar a resposta final."

        while verification_attempt < MAX_VERIFICATION_ATTEMPTS:
            recursion_limit = max(150, prep["max_retries"] * 10 + 50)

            try:
                result = await prep["graph"].ainvoke(
                    {"messages": current_agent_messages},
                    config={**prep["run_config"], "recursion_limit": recursion_limit},
                )
            except GraphRecursionError as recursion_err:
                logger.warning(f"[AgentFactory] ⚠️ Recursion limit reached: {recursion_err}")
                if hasattr(recursion_err, 'args') and len(recursion_err.args) > 1 and 'state' in recursion_err.args[1]:
                    result = recursion_err.args[1]['state']
                else:
                    try:
                        response = await prep["llm"].ainvoke([SystemMessage(content=prep["full_prompt"])] + messages, config=prep["run_config"])
                        return response.content
                    except Exception:
                        return "Desculpe, ocorreu um erro."

            final_messages = result.get("messages", [])
            
            for msg in final_messages:
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        logger.info("[AgentFactory] 🛠️ TOOL_CALL agent='%s' tool=%r", prep["name"], tc.get("name"))
                if isinstance(msg, ToolMessage):
                    logger.info("[AgentFactory] 📨 TOOL_RESULT tool_call_id=%r", msg.tool_call_id)

            logger.info(
                "[AgentFactory] 📊 execution mode=%s actions=%s stop_reason=%s",
                prep["resolved_execution_mode"],
                prep["budget"].actions_used,
                prep["budget"].stop_reason(),
            )

            for msg in reversed(final_messages):
                if isinstance(msg, AIMessage) and msg.content and msg.content.strip():
                    if not (hasattr(msg, "tool_calls") and msg.tool_calls):
                        response_text = msg.content
                        break

            if not response_text or response_text == "Ocorreu um erro ao processar a resposta final.":
                for msg in reversed(final_messages):
                    if isinstance(msg, AIMessage) and msg.content and msg.content.strip():
                        response_text = msg.content
                        break

            # Executa o Verifier Graph
            try:
                verifier_out = await run_verifier(
                    original_message=original_user_msg,
                    response=response_text,
                    messages=final_messages,
                    agent_config=agent_config,
                    llm=prep["llm"],
                    verification_attempt=verification_attempt
                )
                
                if verifier_out.get("status") == "NEED_CORRECTION":
                    correction_instruction = verifier_out.get("correction_instruction")
                    verification_attempt += 1
                    logger.info(f"[AgentFactory] 🔄 Verificador solicitou correção (tentativa {verification_attempt}/{MAX_VERIFICATION_ATTEMPTS}): {correction_instruction[:150] if correction_instruction else ''}")
                    
                    if correction_instruction:
                        current_agent_messages.append(SystemMessage(content=correction_instruction))
                        continue
            except Exception as v_err:
                logger.warning(f"[AgentFactory] ⚠️ Falha ao executar VerifierGraph (liberando resposta por resiliência): {v_err}")

            return response_text

        return response_text


    @staticmethod
    def extract_tool_trace(final_messages, agent_config: dict = None) -> Optional[dict]:
        """Extract tool usage trace from agent execution messages for Q&A Eval.
        Returns a dict with tool_calls, execution_mode, model, and budget info.
        """
        from langchain_core.messages import ToolMessage as _ToolMessage, AIMessage as _AIMessage
        
        tool_calls_trace = []
        for msg in final_messages:
            if isinstance(msg, _AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls_trace.append({
                        "name": tc.get("name"),
                        "args": tc.get("args", {}),
                    })
            if isinstance(msg, _ToolMessage):
                # Match result to the last tool call with same id
                result_preview = str(msg.content)[:500] if msg.content else ""
                # Find matching tool call and add result
                for tc_entry in reversed(tool_calls_trace):
                    if "result_preview" not in tc_entry:
                        tc_entry["result_preview"] = result_preview
                        break

        if not tool_calls_trace:
            return None

        trace = {
            "tool_calls": tool_calls_trace,
        }
        if agent_config:
            trace["execution_mode"] = str(agent_config.get("execution_mode", "balanced"))
            trace["model"] = agent_config.get("model", "unknown")
        return trace

    async def invoke_agent_with_trace(
        self,
        agent_config: Dict[str, Any],
        messages: List[Any],
        rag_context: Optional[str] = None,
        context_data: Optional[Dict[str, Any]] = None,
        execution_mode_override: Optional[str] = None,
    ) -> tuple:
        """Invoke an agent and return (response_text, tool_trace_dict).
        tool_trace_dict may be None if no tools were used.
        """
        prep = await self._prepare_agent_run(agent_config, messages, rag_context, context_data, execution_mode_override)
        
        if not prep["is_react"]:
            response = await prep["llm"].ainvoke(prep["agent_messages"], config=prep["run_config"])
            return response.content, None

        from langgraph.errors import GraphRecursionError
        recursion_limit = max(150, prep["max_retries"] * 10 + 50)

        try:
            result = await prep["graph"].ainvoke(
                {"messages": prep["agent_messages"]},
                config={**prep["run_config"], "recursion_limit": recursion_limit},
            )
        except GraphRecursionError as recursion_err:
            logger.warning(f"[AgentFactory] ⚠️ Recursion limit reached: {recursion_err}")
            if hasattr(recursion_err, 'args') and len(recursion_err.args) > 1 and 'state' in recursion_err.args[1]:
                result = recursion_err.args[1]['state']
            else:
                try:
                    response = await prep["llm"].ainvoke([SystemMessage(content=prep["full_prompt"])] + messages, config=prep["run_config"])
                    return response.content, None
                except Exception:
                    return "Desculpe, ocorreu um erro.", None

        final_messages = result.get("messages", [])
        
        # Extract tool trace
        tool_trace = self.extract_tool_trace(final_messages, agent_config)

        # Logging
        for msg in final_messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    logger.info("[AgentFactory] 🛠️ TOOL_CALL agent='%s' tool=%r", prep["name"], tc.get("name"))
            if isinstance(msg, ToolMessage):
                logger.info("[AgentFactory] 📨 TOOL_RESULT tool_call_id=%r", msg.tool_call_id)

        logger.info(
            "[AgentFactory] 📊 execution mode=%s actions=%s stop_reason=%s",
            prep["resolved_execution_mode"],
            prep["budget"].actions_used,
            prep["budget"].stop_reason(),
        )

        for msg in reversed(final_messages):
            if isinstance(msg, AIMessage) and msg.content and msg.content.strip():
                if not (hasattr(msg, "tool_calls") and msg.tool_calls):
                    return msg.content, tool_trace

        for msg in reversed(final_messages):
            if isinstance(msg, AIMessage) and msg.content and msg.content.strip():
                return msg.content, tool_trace

        return "Ocorreu um erro ao processar a resposta final.", tool_trace

    async def invoke_agent_stream(
        self,
        agent_config: Dict[str, Any],
        messages: List[Any],
        rag_context: Optional[str] = None,
        context_data: Optional[Dict[str, Any]] = None,
        execution_mode_override: Optional[str] = None,
    ):
        """Invoke an agent and stream events/chunks."""
        prep = await self._prepare_agent_run(agent_config, messages, rag_context, context_data, execution_mode_override)
        
        if not prep["is_react"]:
            async for chunk in prep["llm"].astream(prep["agent_messages"], config=prep["run_config"]):
                if chunk.content:
                    yield {"type": "chunk", "data": chunk.content}
            yield {"type": "final", "data": ""}
            return

        recursion_limit = max(150, prep["max_retries"] * 10 + 50)
        
        try:
            async for event in prep["graph"].astream_events(
                {"messages": prep["agent_messages"]},
                config={**prep["run_config"], "recursion_limit": recursion_limit},
                version="v2"
            ):
                kind = event["event"]
                
                # Capture Node changes
                if kind == "on_chain_start" and event["name"] in ["agent", "tools", "force_end"]:
                    yield {"type": "node", "data": event["name"]}
                
                # Capture LLM Chunks
                if kind == "on_chat_model_stream":
                    content = event["data"]["chunk"].content
                    if content:
                        yield {"type": "chunk", "data": content}
                
                # Capture Tool Calls
                if kind == "on_tool_start":
                    yield {
                        "type": "tool_call", 
                        "data": {
                            "name": event["name"],
                            "args": event["data"].get("input")
                        }
                    }
                
                # Capture Tool Results
                if kind == "on_tool_end":
                    yield {
                        "type": "tool_result",
                        "data": {
                            "name": event["name"],
                            "output": str(event["data"].get("output"))
                        }
                    }

            yield {"type": "final", "data": "completed"}
            
        except Exception as e:
            logger.error(f"[AgentFactory] Stream error: {e}")
            yield {"type": "error", "data": str(e)}
    
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
        
        from app.config import get_langfuse_callback
        
        user_phone = None
        sess_id = None
        langfuse_tags = []
        if context_data:
            user_phone = context_data.get("member", {}).get("phone")
            sess_id = context_data.get("session_id")
            instancia_id = context_data.get("global", {}).get("instancia")
            church_id = context_data.get("church", {}).get("_id")
            if instancia_id:
                langfuse_tags.append(f"instancia:{instancia_id}")
            if church_id:
                langfuse_tags.append(f"church:{church_id}")

        callbacks = []
        langfuse_cb = get_langfuse_callback()
        if langfuse_cb:
            callbacks.append(langfuse_cb)
            
        metadata = {
            "agent_id": agent_config["id"],
            "agent_name": agent_config["name"],
            "has_tools": agent_config.get("has_tools", False),
            "model": agent_config["model"],
            "structured": True
        }
        
        if user_phone: metadata["langfuse_user_id"] = user_phone
        if sess_id: metadata["langfuse_session_id"] = sess_id
        if langfuse_tags: metadata["langfuse_tags"] = langfuse_tags

        # Create config for structured output tracing
        run_config = RunnableConfig(
            run_name=agent_config["name"],
            metadata=metadata,
            tags=[f"agent:{agent_config['name']}", "structured"],
            callbacks=callbacks if callbacks else None
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
                    
                    logger.info(f"[AgentFactory] 🛡️ Pruned {paths_pruned_count} request-only field(s) from prompt context in structured mode.")
                    
                    # Use the pruned copy for formatting
                    context_section = format_context_data_for_prompt(context_data_for_prompt, input_schema)
                else:
                    context_section = format_context_data_for_prompt(context_data, input_schema)
            except Exception as e:
                logger.warning(f"[AgentFactory] Failed to get MCP metadata for strict filtering in structured mode: {e}")
                # Fallback: format context without pruning so the agent still works
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
            
        trimmed_structured_msgs = _clean_and_trim_messages(messages, max_history=8, for_tools=True)
        all_messages = [SystemMessage(content=system_prompt)] + trimmed_structured_msgs
        
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

