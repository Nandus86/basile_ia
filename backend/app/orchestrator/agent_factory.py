"""
Agent Factory - Creates LangGraph-compatible agents from database configurations
"""
from typing import List, Optional, Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import create_react_agent
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.agent import Agent, AccessLevel
from app.config import settings
from app.orchestrator.callbacks import build_cost_callbacks

import logging
import json
import copy
import urllib.parse
logger = logging.getLogger(__name__)


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
        }
        
        self._agent_cache[agent_id] = config
        return config
    
    def create_llm(self, agent_config: Dict[str, Any]) -> ChatOpenAI:
        """Create LLM instance for an agent, routing to the correct provider.
        Supports reasoning models (O1, O3, DeepSeek R1) with special parameters.
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
            
            kwargs["temperature"] = 1  # reasoning models require temperature=1
            kwargs["model_kwargs"] = {
                "reasoning_effort": reasoning_effort,
                "max_completion_tokens": max_completion_tokens
            }
        else:
            # Traditional models: use temperature and max_tokens
            kwargs["temperature"] = agent_config.get("temperature", 0.7)
            kwargs["max_tokens"] = agent_config.get("max_tokens", 2048)
        
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
                logger.info(f"[AgentFactory] 🌐 Usando provedor customizado '{provider.name}' na URL '{base_url}' para o modelo '{model_id}'")
            else:
                logger.info(f"[AgentFactory] 🌐 Usando provedor customizado '{provider.name}' (sem base_url) para o modelo '{model_id}'")
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

    async def _inject_dynamic_skills(self, agent_config: Dict[str, Any], messages: List[Any], system_prompt: str) -> str:
        """Inject skills dynamically based on user intent."""
        from langchain_core.messages import HumanMessage
        
        last_user_content = ""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage) and msg.content:
                last_user_content = str(msg.content)
                break
                
        if not last_user_content:
            return system_prompt
            
        agent = agent_config.get("agent_model")
        if not agent or not getattr(agent, "skills", None):
            return system_prompt
            
        active_skills_for_detection = [s for s in agent.skills if s.is_active]
        if not active_skills_for_detection:
            return system_prompt
            
        try:
            from app.orchestrator.skill_router import SkillRouter
            from app.services.skill_detector import get_skill_content_for_capability, extract_all_flows
            
            router = SkillRouter()
            skill_route = await router.analyze(last_user_content, active_skills_for_detection)
            
            if skill_route:
                skill = skill_route["skill"]
                forced = skill_route.get("forced", False)
                
                all_flows = extract_all_flows(skill)
                
                if all_flows:
                    flows_text = "\n\n".join([
                        f"### Etapa {f['etapa']}\n{f['flow']}\n" + 
                        ("⚠️ **AGUARDE RESPOSTA DO USUÁRIO ANTES DE CONTINUAR**\n" if f['has_hitl'] else "")
                        for f in all_flows
                    ])
                    
                    flow_injection = f"\n---\n\n## 🎯 FLUXO DE EXECUÇÃO - {skill.name}\n\nSiga as etapas ABAIXO NA ORDEM EXATA, SEM PULAR ETAPAS:\n\n{flows_text}\n\n---\n"
                    system_prompt += flow_injection
                    logger.info(f"[AgentFactory] 🎯 Injected {len(all_flows)} flow(s) from skill '{skill.name}' (via Skill Router)")
                else:
                    if forced:
                        capabilities = skill_route.get("capabilities", [])
                        injected_count = 0
                        for cap in capabilities:
                            cap_content = get_skill_content_for_capability(skill, cap["header"])
                            if cap_content:
                                skill_injection = f"\n---\n\n## 🔹 CAPABILITY ATIVADA: {cap['header']}\n\n{cap_content}\n\n---\n"
                                system_prompt += skill_injection
                                injected_count += 1
                        
                        if injected_count == 0 and skill.content_md:
                            skill_injection = f"\n---\n\n## 🔹 CAPABILITIES DA SKILL ATIVA: {skill.name}\n\n{skill.content_md}\n\n---\n"
                            system_prompt += skill_injection
                            
                        logger.info(f"[AgentFactory] 🎯 Injected ALL capabilities ({injected_count}) from always_active skill '{skill.name}'")
                    else:
                        capability = skill_route.get("capability")
                        if capability:
                            capability_content = get_skill_content_for_capability(skill, capability["header"])
                            if capability_content:
                                skill_injection = f"\n---\n\n## 🔹 CAPABILITY ATIVADA: {capability['header']}\n\n{capability_content}\n\n---\n"
                                system_prompt += skill_injection
                                logger.info(f"[AgentFactory] 🎯 Injected skill capability '{capability['header']}' from skill '{skill.name}'")
        except Exception as e:
            import traceback
            logger.error(f"[AgentFactory] Failed to detect and inject skills: {e}")
            traceback.print_exc()
            
        return system_prompt
    
    async def invoke_agent(
        self,
        agent_config: Dict[str, Any],
        messages: List[Any],
        rag_context: Optional[str] = None,
        context_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Invoke an agent with messages and return response.
        Uses ReAct if agent has tools, otherwise simple LLM call.
        """
        from app.schemas.structured_output import format_context_data_for_prompt
        
        llm = self.create_llm(agent_config)
        run_config = self.get_run_config(agent_config)
        
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
        
        # Inject Dynamic Skills (using new LLM-based router)
        system_prompt = await self._inject_dynamic_skills(agent_config, messages, system_prompt)
        
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
        
        if agent_config["has_tools"]:
            # Use ReAct agent with tools
            tool_list = "\n".join([f"- **{t.name}**: {t.description}" for t in agent_config["tools"]])
            # Add skills reminder before tools (so the LLM sees them together)
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
"""
            full_prompt = system_prompt + tool_instructions
            
            agent_messages = [SystemMessage(content=full_prompt)] + messages
            
            react_agent = create_react_agent(
                model=llm,
                tools=agent_config["tools"]
            )

            logger.info(
                f"[AgentFactory] 🤖 Invocando ReAct agent='{agent_config['name']}'  "
                f"model='{agent_config['model']}'  tools={[t.name for t in agent_config['tools']]}"
            )
            recursion_limit = max(12, max_retries * 4 + 4)
            result = await react_agent.ainvoke(
                {"messages": agent_messages},
                config={
                    **run_config,
                    "recursion_limit": recursion_limit  # Prevent infinite tool loops dynamically based on max_retries
                }
            )

            # Log tool calls executed during this run
            from langchain_core.messages import ToolMessage
            final_messages = result.get("messages", [])
            for msg in final_messages:
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        logger.info(
                            f"[AgentFactory] 🛠️  TOOL_CALL  agent='{agent_config['name']}'  "
                            f"tool={tc.get('name')!r}  args={json.dumps(tc.get('args', {}), default=str, ensure_ascii=False)[:400]}"
                        )
                if isinstance(msg, ToolMessage):
                    logger.info(
                        f"[AgentFactory] 📨 TOOL_RESULT  tool_call_id={msg.tool_call_id!r}  "
                        f"preview={str(msg.content)[:400]!r}"
                    )

            # Extract final response
            for msg in reversed(final_messages):
                if isinstance(msg, AIMessage) and msg.content and msg.content.strip():
                    if not (hasattr(msg, "tool_calls") and msg.tool_calls):
                        return msg.content
            
            # Fallback: if the last AIMessage has tool_calls but the loop ended, 
            # or if content is empty, look for the last non-empty AIMessage
            for msg in reversed(final_messages):
                if isinstance(msg, AIMessage) and msg.content and msg.content.strip():
                    return msg.content
            
            # If all AIMessages are empty and there were tool calls, the model 
            # might be waiting for a final nudge or the react_agent didn't finish.
            # But here we simply report the failure or return a safe default.
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
        context_data: Optional[Dict[str, Any]] = None
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
        
        # Inject Dynamic Skills (using new LLM-based router)
        system_prompt = await self._inject_dynamic_skills(agent_config, messages, system_prompt)
        
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
                                fallback_text = await self.invoke_agent(agent_config, messages, rag_context, context_data)
                                partial_data["output"] = fallback_text
                                
                            return partial_data
                except Exception as inner_e:
                    logger.error(f"[AgentFactory] ❌ Falha ao recuperar JSON parcial: {inner_e}")
            
            # Fallback final se falhar e não recuperar JSON parcial
            regular_response = await self.invoke_agent(agent_config, messages, rag_context, context_data)
            return {"output": regular_response}

