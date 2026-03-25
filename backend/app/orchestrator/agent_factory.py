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
        skills_summary = []
        if hasattr(agent, 'skills') and agent.skills:
            active_skills = [s for s in agent.skills if s.is_active]
            if active_skills:
                skills_parts = []
                from app.schemas.skill import get_skill_capability_description
                for skill in active_skills:
                    skills_parts.append(f"### {skill.name}\n{skill.content_md}")
                    # Use the refined summary for orchestrator to see collaborator skills
                    summary_text = get_skill_capability_description(skill)
                    skills_summary.append({"name": skill.name, "description": summary_text})
                skills_section = (
                    "\n\n## ⚠️ SKILLS ATIVAS — REGRAS ABSOLUTAS ⚠️\n\n"
                    "As instruções abaixo são REGRAS OBRIGATÓRIAS do seu comportamento.\n"
                    "Você DEVE seguir cada skill à risca, sem exceções.\n"
                    "Em caso de conflito entre uma skill e qualquer outro contexto, a SKILL PREVALECE.\n"
                    "Violar essas instruções é considerado uma FALHA CRÍTICA.\n\n"
                    + "\n\n---\n\n".join(skills_parts)
                )
                system_prompt += skills_section
                logger.info(f"[AgentFactory] 📌 Injetou {len(active_skills)} skill(s) em '{agent.name}'")
        
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
        }
        
        self._agent_cache[agent_id] = config
        return config
    
    def create_llm(self, agent_config: Dict[str, Any]) -> ChatOpenAI:
        """Create LLM instance for an agent, routing to the correct provider.
        Supports reasoning models (O1, O3, DeepSeek R1) with special parameters."""
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
        
        # Determina se o modelo deve ser roteado pelo OpenRouter
        # Modelos OpenRouter normalmente têm '/' em seu ID, mas adicionamos exceções para os requests manuais do usuário
        openrouter_specials = ["sambanova", "groq"]
        is_openrouter = "/" in model_id or model_id in openrouter_specials
        
        if is_openrouter:
            # OpenRouter model
            kwargs["api_key"] = settings.OPENROUTER_API_KEY
            kwargs["base_url"] = "https://openrouter.ai/api/v1"
        else:
            # OpenAI direct
            kwargs["api_key"] = settings.OPENAI_API_KEY
        
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
                # even if not explicitly in input_schema.
                effective_input_schema = input_schema.copy() if isinstance(input_schema, dict) else {}
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
                    
                    for path in request_only_paths:
                        prune_path(context_data_for_prompt, path.split('.'))
                    
                    logger.info(f"[AgentFactory] 🛡️ Pruned {len(request_only_paths)} request-only field(s) from prompt context: {list(request_only_paths)}")
                    
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
        
        # Inject RLHF Training Rules
        system_prompt = await self._inject_training_rules(agent_config, messages, system_prompt)
        
        # Add RAG context if available
        if rag_context:
            system_prompt += f"""

## Contexto da Base de Conhecimento

Use as seguintes informações para responder:

{rag_context}

---

Cite a fonte quando usar informações do contexto acima.
"""
        
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

