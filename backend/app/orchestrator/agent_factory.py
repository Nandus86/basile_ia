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
            tools = await get_tools_for_agent(self.db, agent_id, filtered_context)
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
                from app.schemas.skill import get_skill_capability_description
                for skill in active_skills:
                    skills_parts.append(f"### {skill.name}\n{skill.content_md}")
                    # Use the refined summary for orchestrator to see collaborator skills
                    summary_text = get_skill_capability_description(skill)
                    skills_summary.append({"name": skill.name, "description": summary_text})
                skills_section = (
                    "\n\n## Skills e Instruções Especializadas\n\n"
                    "Siga estritamente as instruções abaixo como parte do seu comportamento:\n\n"
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
            context_section = format_context_data_for_prompt(context_data, input_schema)
            if context_section:
                system_prompt += context_section
        
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
            tool_instructions = f"""

## Árvore de Ferramentas / MCPs Disponíveis
Você tem acesso às seguintes ferramentas (MCPs). Relacione os passos solicitados nas suas skills com os nomes listados abaixo, que são os métodos reais que você pode invocar:
{tool_list}

## Instruções de Ferramentas e Resiliência (MUITO IMPORTANTE)

Você tem ferramentas locais e remotas (MCP) disponíveis. USE-AS SEMPRE que necessário para completar suas tarefas ou consultar o banco.
 REGRA CRÍTICA DE RETENTATIVA: Se a execução de uma ferramenta retornar qualquer ERRO, "Falha", ou avisar que campos estão indisponíveis, você **NÃO DEVE DESISTIR** imediatamente.
- Você DEVE TENTAR EXECUTAR A FERRAMENTA NOVAMENTE AO MENOS MAIS DUAS VEZES (totalizando 3 tentativas), corrigindo, omitindo ou variando os parâmetros enviados com base no seu entendimento da conversa.
- Somente se falhar definitivamente após as 3 tentativas consecutivas, explique ao usuário detalhadamente o porquê da falha baseado na mensagem de erro que a ferramenta devolveu.
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
            result = await react_agent.ainvoke(
                {"messages": agent_messages},
                config=run_config
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
                if isinstance(msg, AIMessage) and msg.content:
                    if not (hasattr(msg, "tool_calls") and msg.tool_calls):
                        return msg.content
            
            # Fallback
            for msg in reversed(final_messages):
                if isinstance(msg, AIMessage) and msg.content:
                    return msg.content
            
            return "Não foi possível gerar uma resposta."
        
        else:
            # Simple LLM call
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

