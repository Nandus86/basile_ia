"""
LangGraph Orchestrator with Access Levels, Agent Collaboration and MCP Tools
"""
from langgraph.graph import StateGraph, END
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

from app.orchestrator.state import OrchestratorState
from app.models.agent import Agent, AccessLevel
from app.config import settings


# Initialize LLM
def get_llm():
    """Get LLM instance"""
    return ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.7,
        api_key=settings.OPENAI_API_KEY
    )


# ==================== Node Functions ====================

async def select_specialist_agent(state: OrchestratorState, db: AsyncSession) -> OrchestratorState:
    """
    Select the most appropriate specialist agent based on message context.
    Uses LLM to analyze the message and match with available agents.
    Filters by user's access level.
    """
    agent_id = state.get("agent_id")
    user_access_level = state.get("user_access_level", "normal")
    
    # Convert to enum
    try:
        user_level = AccessLevel(user_access_level)
    except ValueError:
        user_level = AccessLevel.NORMAL
    
    user_level_value = AccessLevel.get_level_value(user_level)
    
    if agent_id:
        # Use specific agent (if user has access)
        result = await db.execute(
            select(Agent)
            .options(
                selectinload(Agent.mcps),
                selectinload(Agent.skills)
            )
            .where(Agent.id == agent_id, Agent.is_active == True)
        )
        agent = result.scalar_one_or_none()
        
        # Check access level
        if agent and AccessLevel.get_level_value(agent.access_level) > user_level_value:
            print(f"[Agent Selection] User level {user_access_level} cannot access agent {agent.name} (level {agent.access_level.value})")
            agent = None
    else:
        # Get all active agents accessible to user's level
        result = await db.execute(
            select(Agent)
            .options(
                selectinload(Agent.mcps),
                selectinload(Agent.skills)
            )
            .where(Agent.is_active == True)
        )
        all_agents = result.scalars().all()
        
        # Filter by access level
        accessible_agents = [
            a for a in all_agents 
            if AccessLevel.get_level_value(a.access_level) <= user_level_value
        ]
        
        print(f"[Agent Selection] User level {user_access_level}: {len(accessible_agents)}/{len(all_agents)} agents accessible")
        
        if not accessible_agents:
            state["selected_agent"] = None
            state["agent_used"] = "default"
            return state
        
        # Use LLM to select the best agent
        if len(accessible_agents) == 1:
            agent = accessible_agents[0]
        else:
            agent = await _select_agent_with_llm(state["message"], accessible_agents)
    
    if agent:
        state["selected_agent"] = {
            "id": str(agent.id),
            "name": agent.name,
            "system_prompt": agent.system_prompt,
            "model": agent.model,
            "temperature": float(agent.temperature),
            "max_tokens": int(agent.max_tokens),
            "access_level": agent.access_level.value,
            "collaboration_enabled": agent.collaboration_enabled,
            "vector_memory_enabled": getattr(agent, "vector_memory_enabled", False) and (agent.config.get("memory_enabled", True) if getattr(agent, "config", None) else True)
        }
        state["agent_used"] = agent.name
        state["agent_model"] = agent  # Store full model for orchestration
    else:
        state["selected_agent"] = None
        state["agent_used"] = "default"
    
    return state


async def _select_agent_with_llm(message: str, agents: List[Agent]) -> Optional[Agent]:
    """Use LLM to select the best agent for the message"""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=settings.OPENAI_API_KEY)
    
    # Build agent descriptions
    agent_descriptions = []
    for agent in agents:
        details = []
        
        # Capability Map (Skills + Intents)
        if hasattr(agent, 'skills') and agent.skills:
            from app.schemas.skill import get_skill_capability_description
            active_skills = [s for s in agent.skills if s.is_active]
            if active_skills:
                skills_text = ", ".join([
                    f"{s.name}: {get_skill_capability_description(s)}"
                    for s in active_skills
                ])
                details.append(f"CAPACIDADES: {skills_text}")
        
        # Tool Map (MCPs)
        mcp_names = [m.name for m in agent.mcps] if agent.mcps else []
        if mcp_names:
            details.append(f"FERRAMENTAS: {', '.join(mcp_names)}")
        
        details_str = "\n".join(details)
        desc = f"""
AGENTE: {agent.name}
ID: {agent.id}
DESCRIÇÃO: {agent.description or 'Sem descrição'}
{details_str}
"""
        agent_descriptions.append(desc)
    
    agents_str = "\n---\n".join(agent_descriptions)
    
    selector_prompt = f"""Você é um roteador especializado. Analise a mensagem e escolha o agente mais adequado.

REGRAS DE ESCOLHA:
1. Analise as CAPACIDADES e FERRAMENTAS listadas para cada agente.
2. Certifique-se de que o agente selecionado tem o escopo e as habilidades necessárias para resolver a solicitação.
3. Se o usuário pedir uma ação (ex: agendar, buscar), use agentes que possuam ferramentas para isso.

MENSAGEM: "{message}"

AGENTES DISPONÍVEIS:
{agents_str}

Responda APENAS com o ID do agente (UUID) ou "NENHUM". Sem explicações."""
    
    try:
        response = await llm.ainvoke([SystemMessage(content=selector_prompt)])
        selected_id = response.content.strip()
        
        if selected_id.upper() == "NENHUM":
            return agents[0] if agents else None
        
        for agent in agents:
            if str(agent.id) == selected_id:
                return agent
        
        return agents[0] if agents else None
    except Exception as e:
        print(f"[Agent Selection] LLM error: {e}")
        return agents[0] if agents else None


async def generate_response(state: OrchestratorState, db: AsyncSession = None) -> OrchestratorState:
    """Generate response using LLM with MCP tools, RAG, and optionally orchestrate with collaborators"""
    try:
        llm = get_llm()
        
        # Get agent info
        agent_info = state.get("selected_agent")
        agent_model = state.get("agent_model")
        agent_id = agent_info.get("id") if agent_info else None
        
        # Build system prompt
        if agent_info and agent_info.get("system_prompt"):
            system_prompt = agent_info["system_prompt"]
        else:
            system_prompt = "You are a helpful AI assistant. Respond in the same language as the user."
        
        # Get RAG context if agent has documents
        rag_context = ""
        if agent_id and db:
            try:
                from app.services.rag_service import get_rag_context
                rag_context = await get_rag_context(db, agent_id, state["message"], limit=5)
                if rag_context:
                    print(f"[Response] 📚 Retrieved RAG context for agent {agent_info.get('name', 'unknown')}")
                    # Enhance system prompt with RAG context
                    system_prompt += f"""

## Contexto da Base de Conhecimento

Use as seguintes informações da base de conhecimento para responder ao usuário:

{rag_context}

---

Cite a fonte (nome do documento) quando usar informações do contexto acima.
"""
            except Exception as e:
                print(f"[Response] Failed to get RAG context: {e}")
                
        # Get Intelligent Vector Memory (Contact qualitative data)
        contact_id = state.get("session_id") # Use session_id as the surrogate contact identifier
        current_message = state["message"]
        
        # Information Bases Retrieval
        info_base_context_data = state.get("context_data") or {}
        if agent_id and db:
            try:
                from app.models.agent import Agent
                from sqlalchemy import select
                from sqlalchemy.orm import selectinload
                result = await db.execute(
                    select(Agent).options(selectinload(Agent.information_bases)).where(Agent.id == agent_id)
                )
                agent_obj = result.scalar_one_or_none()
                if agent_obj and agent_obj.information_bases:
                    active_bases = [b for b in agent_obj.information_bases if b.is_active]
                    if active_bases:
                        from app.weaviate_client import get_weaviate
                        weaviate_client = get_weaviate()
                        all_info_nodes = []
                        ib_global_search = getattr(agent_obj, "information_bases_global_search_enabled", False)

                        if weaviate_client:
                            if ib_global_search:
                                possible_ids = []
                                for ib in active_bases:
                                    if ib.correlation_schema and isinstance(ib.correlation_schema, dict):
                                        target_key = ib.correlation_schema.get("target")
                                        if target_key:
                                            clean_target = target_key.strip()
                                            if clean_target.startswith("$request."):
                                                clean_target = clean_target[len("$request."):]
                                            parts = clean_target.split(".")
                                            val = info_base_context_data
                                            for part in parts:
                                                if isinstance(val, dict) and part in val:
                                                    val = val[part]
                                                else:
                                                    val = None
                                                    break
                                            if val is not None and not isinstance(val, (dict, list)):
                                                v_str = str(val).strip()
                                                if v_str:
                                                    possible_ids.append(v_str)

                                if not possible_ids:
                                    for k, v in info_base_context_data.items():
                                        if isinstance(v, str) and v.strip():
                                            possible_ids.append(v.strip())
                                    if contact_id:
                                        possible_ids.append(str(contact_id))

                                possible_ids = list(dict.fromkeys(possible_ids))
                                base_codes = [ib.code for ib in active_bases if ib.code]
                                ib_limit = max([getattr(ib, 'max_results', 3) or 3 for ib in active_bases] or [3])
                                for uid in possible_ids:
                                    info_nodes = await weaviate_client.search_information_bases(
                                        base_codes=base_codes,
                                        user_id=uid,
                                        query=current_message,
                                        limit=ib_limit
                                    )
                                    if info_nodes:
                                        all_info_nodes.extend(info_nodes)
                            else:
                                for ib in active_bases:
                                    possible_ids = []
                                    # Try extraction via correlation_schema
                                    if ib.correlation_schema and isinstance(ib.correlation_schema, dict):
                                        target_key = ib.correlation_schema.get("target")
                                        if target_key:
                                            clean_target = target_key.strip()
                                            if clean_target.startswith("$request."):
                                                clean_target = clean_target[len("$request."):]
                                            parts = clean_target.split(".")
                                            val = info_base_context_data
                                            for part in parts:
                                                if isinstance(val, dict) and part in val:
                                                    val = val[part]
                                                else:
                                                    val = None
                                                    break
                                            if val is not None and not isinstance(val, (dict, list)):
                                                v_str = str(val).strip()
                                                if v_str:
                                                    possible_ids.append(v_str)

                                    # Fallback to general context scanning if no specific id was found
                                    if not possible_ids:
                                        for k, v in info_base_context_data.items():
                                            if isinstance(v, str) and v.strip():
                                                possible_ids.append(v.strip())
                                        if contact_id:
                                            possible_ids.append(str(contact_id))

                                    possible_ids = list(dict.fromkeys(possible_ids))
                                    # Fetch nodes uniquely for this base's IDs
                                    for uid in possible_ids:
                                        info_nodes = await weaviate_client.search_information_bases(
                                            base_codes=[ib.code],
                                            user_id=uid,
                                            query=current_message,
                                            limit=getattr(ib, 'max_results', 3) or 3
                                        )
                                        if info_nodes:
                                            all_info_nodes.extend(info_nodes)

                            if all_info_nodes:
                                # Deduplicate by content
                                seen = set()
                                unique_nodes = []
                                for n in all_info_nodes:
                                    if n['content'] not in seen:
                                        seen.add(n['content'])
                                        unique_nodes.append(n)
                                print(f"[Response] 📚 Retrieved {len(unique_nodes)} Information Base contexts")
                                info_str = "\n".join([f"- {n['content']} (Meta: {n['metadata']})" for n in unique_nodes[:6]])
                                system_prompt += f"\n\n## Contextualização Personalizada Externa\n\nInformações anexadas aos bancos de dados do usuário logado:\n{info_str}\n"

            except Exception as e:
                import traceback
                print(f"[Response] Failed to retrieve Information Bases context: {e}")
                traceback.print_exc()
        
        if vector_memory_enabled and agent_id and contact_id:
            try:
                from app.weaviate_client import get_weaviate
                weaviate_client = get_weaviate()
                if weaviate_client:
                    memories = await weaviate_client.search_contact_memories(
                        agent_id=str(agent_id),
                        contact_id=str(contact_id),
                        query=current_message,
                        limit=5
                    )
                    
                    if memories:
                        print(f"[VectorMemory] 🧠 Retrieved {len(memories)} qualitative facts for contact {contact_id}")
                        mem_str = "\n".join([f"- {m['content']}" for m in memories])
                        
                        system_prompt += f"""

## Inteligência e Memória Histórica do Contato

Abaixo estão informações e peculiaridades qualitativas deste usuário, adquiridas em interações anteriores. 
Utilize isso para personalizar ativamente o engajamento de maneira natural:

{mem_str}
"""
                        
            except Exception as e:
                import traceback
                print(f"[VectorMemory] Failed to retrieve vector memory: {e}")
                traceback.print_exc()

        # Extract New Vector Memories in background asynchronously (only for substantive interactions)
        if vector_memory_enabled and agent_id and contact_id:
            try:
                from app.services.memory_gate import should_extract_memories
                if should_extract_memories(current_message, history=state.get("history", [])):
                    from app.services.vector_memory_service import extract_and_save_memories
                    import asyncio
                    # Fire and forget into the event loop
                    history_copy = state.get("history", [])[:]
                    asyncio.create_task(
                        extract_and_save_memories(
                            agent_id=str(agent_id),
                            contact_id=str(contact_id),
                            history=history_copy,
                            current_message=current_message
                        )
                    )
            except Exception as e:
                print(f"[VectorMemory] Failed to launch extraction task: {e}")
        
        # Load agent config for resilience settings
        agent_config = None
        if agent_id and db:
            try:
                from app.models.agent_config import AgentConfig
                result = await db.execute(
                    select(AgentConfig).where(AgentConfig.agent_id == agent_id)
                )
                agent_config = result.scalar_one_or_none()
                if agent_config and agent_config.verbose_logging:
                    print(f"[Response] ⚙️ Config loaded: retries={agent_config.max_retries}, timeout={agent_config.timeout_seconds}s")
            except Exception as e:
                print(f"[Response] Failed to load agent config: {e}")
        
        # Build conversation messages (for history)
        messages = []
        for msg in state.get("history", []):
            timestamp = msg.get("created_at") or msg.get("timestamp")
            prefix = f"[{timestamp}] " if timestamp else ""
            
            if msg.get("role") == "user":
                messages.append(HumanMessage(content=f"{prefix}{msg['content']}"))
            elif msg.get("role") == "assistant":
                from langchain_core.messages import AIMessage
                messages.append(AIMessage(content=f"{prefix}{msg['content']}"))
        
        # Add current message
        messages.append(HumanMessage(content=state["message"]))
        
        # Try to get MCP tools for the agent
        tools = []
        if agent_id and db:
            try:
                from app.services.mcp_tools import get_tools_for_agent
                tools = await get_tools_for_agent(db, agent_id)
                if tools:
                    print(f"[Response] 🔧 Loaded {len(tools)} MCP tools for agent {agent_info.get('name', 'unknown')}")
            except Exception as e:
                print(f"[Response] Failed to load MCP tools: {e}")
        
        # Dynamic Skill Detection - inject skill if needed based on user message
        active_skills_for_detection = []
        if agent_id and db:
            try:
                from app.models.agent import Agent
                from sqlalchemy import select
                from sqlalchemy.orm import selectinload
                result = await db.execute(
                    select(Agent).options(selectinload(Agent.skills)).where(Agent.id == agent_id)
                )
                agent_obj = result.scalar_one_or_none()
                if agent_obj and agent_obj.skills:
                    active_skills_for_detection = [s for s in agent_obj.skills if s.is_active]
                    if active_skills_for_detection:
                        print(f"[Response] 🎯 Found {len(active_skills_for_detection)} active skills for detection")
                        
                        from app.orchestrator.skill_router import SkillRouter
                        from app.services.skill_detector import get_skill_content_for_capability, extract_all_flows
                        
                        router = SkillRouter()
                        skill_route = await router.analyze(state["message"], active_skills_for_detection)
                        
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
                                
                                flow_injection = f"""

---

## 🎯 FLUXO DE EXECUÇÃO - {skill.name}

Siga as etapas ABAIXO NA ORDEM EXATA, SEM PULAR ETAPAS:

{flows_text}

---
"""
                                system_prompt += flow_injection
                                print(f"[Response] 🎯 Injected {len(all_flows)} flow(s) from skill '{skill.name}' (via Skill Router)")
                            else:
                                if forced:
                                    capabilities = skill_route.get("capabilities", [])
                                    injected_count = 0
                                    for cap in capabilities:
                                        cap_content = get_skill_content_for_capability(skill, cap["header"])
                                        if cap_content:
                                            skill_injection = f"""

---

## 🔹 CAPABILITY ATIVADA: {cap['header']}

{cap_content}

---

"""
                                            system_prompt += skill_injection
                                            injected_count += 1
                                    
                                    # Fallback caso não existam headers válidos na skill Sempre Ativa
                                    if injected_count == 0 and skill.content_md:
                                        skill_injection = f"""

---

## 🔹 CAPABILITIES DA SKILL ATIVA: {skill.name}

{skill.content_md}

---

"""
                                        system_prompt += skill_injection
                                        
                                    print(f"[Response] 🎯 Injected ALL capabilities ({injected_count}) from always_active skill '{skill.name}'")
                                else:
                                    capability = skill_route.get("capability")
                                    if capability:
                                        capability_content = get_skill_content_for_capability(skill, capability["header"])
                                        if capability_content:
                                            skill_injection = f"""

---

## 🔹 CAPABILITY ATIVADA: {capability['header']}

{capability_content}

---

"""
                                            system_prompt += skill_injection
                                            print(f"[Response] 🎯 Injected skill capability '{capability['header']}' from skill '{skill.name}'")
            except Exception as e:
                import traceback
                print(f"[Response] Failed to detect and inject skills: {e}")
                traceback.print_exc()
        
        # Generate response with or without tools
        if tools:
            # Use ReAct agent with tools
            try:
                # Add system message to the messages list
                tool_list = "\n".join([f"- **{t.name}**: {t.description}" for t in tools])
                tool_instructions = f"""

## Árvore de Ferramentas / MCPs Disponíveis
Você tem acesso às seguintes ferramentas (MCPs). Relacione os passos solicitados nas suas skills com os nomes listados abaixo, que são os métodos reais que você pode invocar:
{tool_list}

Você tem acesso a ferramentas externas. USE-AS ATIVAMENTE quando o usuário pedir ações como agendamentos, consultas, etc. Sempre responda no mesmo idioma do usuário."""
                full_prompt = system_prompt + tool_instructions
                
                # Insert SystemMessage at the beginning
                agent_messages = [SystemMessage(content=full_prompt)] + messages
                
                agent = create_react_agent(
                    model=llm,
                    tools=tools
                )
                
                result = await agent.ainvoke({"messages": agent_messages})
                
                # Extract final response and log tool calls
                final_messages = result.get("messages", [])
                print(f"[Response] 📬 Got {len(final_messages)} messages from agent")
                
                if final_messages:
                    # Log all messages for debugging
                    for i, msg in enumerate(final_messages):
                        msg_type = type(msg).__name__
                        has_tool_calls = hasattr(msg, "tool_calls") and msg.tool_calls
                        content_preview = (msg.content[:50] + "...") if hasattr(msg, "content") and msg.content else "(empty)"
                        print(f"[Response] Message {i}: {msg_type}, tool_calls={has_tool_calls}, content={content_preview}")
                        
                        if has_tool_calls:
                            for tc in msg.tool_calls:
                                print(f"[Response] 🔧 Tool called: {tc.get('name', 'unknown')}")
                    
                    # Get the last AI message with content (that isn't just a tool call request)
                    from langchain_core.messages import AIMessage
                    response_text = None
                    for msg in reversed(final_messages):
                        if isinstance(msg, AIMessage) and msg.content:
                            # Check if this is just a tool call message (has tool_calls but we want the final response)
                            if not (hasattr(msg, "tool_calls") and msg.tool_calls):
                                response_text = msg.content
                                print(f"[Response] 🤖 Using AIMessage with content")
                                break
                    
                    # Fallback: get any message with content
                    if not response_text:
                        for msg in reversed(final_messages):
                            if hasattr(msg, "content") and msg.content and isinstance(msg, AIMessage):
                                response_text = msg.content
                                print(f"[Response] 🤖 Fallback: using last AIMessage with content")
                                break
                    
                    if not response_text:
                        response_text = "Não consegui gerar uma resposta. Por favor, tente novamente."
                else:
                    response_text = "Nenhuma resposta gerada."
                    
            except Exception as e:
                print(f"[Response] ReAct agent error, falling back to simple LLM: {e}")
                import traceback
                traceback.print_exc()
                # Fallback to simple LLM
                simple_messages = [{"role": "system", "content": system_prompt}]
                simple_messages.extend([{"role": m.get("role"), "content": m.get("content")} for m in state.get("history", [])])
                simple_messages.append({"role": "user", "content": state["message"]})
                response = await llm.ainvoke(simple_messages)
                response_text = response.content
        else:
            # Standard LLM call without tools
            simple_messages = [{"role": "system", "content": system_prompt}]
            for msg in state.get("history", []):
                simple_messages.append(msg)
            simple_messages.append({"role": "user", "content": state["message"]})
            
            response = await llm.ainvoke(simple_messages)
            response_text = response.content
        
        # Check if we should orchestrate with collaborators
        if agent_model and db and agent_info.get("collaboration_enabled", False):
            try:
                from app.orchestrator.agent_orchestrator import AgentOrchestrator
                orchestrator = AgentOrchestrator(db)
                
                # Run orchestration
                orchestrated_response = await orchestrator.orchestrate(
                    message=state["message"],
                    primary_agent=agent_model,
                    primary_response=response_text,
                    context=""
                )
                
                if orchestrated_response != response_text:
                    print(f"[Response] 🎭 Orchestrator enhanced response with collaborators")
                    response_text = orchestrated_response
                    
            except Exception as e:
                print(f"[Response] Orchestrator error (using original response): {e}")
        
        state["response"] = response_text
        
    except Exception as e:
        state["response"] = f"Error generating response: {str(e)}"
        state["error"] = str(e)
    
    return state


# ==================== Graph Builder ====================

def create_graph(db: AsyncSession):
    """Create the orchestrator graph"""
    
    async def select_agent_node(state: OrchestratorState) -> OrchestratorState:
        return await select_specialist_agent(state, db)
    
    async def generate_response_node(state: OrchestratorState) -> OrchestratorState:
        return await generate_response(state, db)
    
    # Create graph
    graph = StateGraph(OrchestratorState)
    
    # Add nodes
    graph.add_node("select_agent", select_agent_node)
    graph.add_node("generate_response", generate_response_node)
    
    # Define edges
    graph.set_entry_point("select_agent")
    graph.add_edge("select_agent", "generate_response")
    graph.add_edge("generate_response", END)
    
    return graph.compile()


# ==================== Main Runner ====================

async def run_orchestrator(
    message: str,
    session_id: str,
    history: List[Dict[str, str]],
    agent_id: Optional[str],
    db: AsyncSession,
    user_access_level: str = "normal"
) -> Dict[str, Any]:
    """
    Run the orchestrator graph.
    
    Args:
        message: User message
        session_id: Session identifier
        history: Conversation history
        agent_id: Optional specific agent ID
        db: Database session
        user_access_level: User's access level (minimum/normal/pro/premium)
        
    Returns:
        Dict with response and agent_used
    """
    # Create initial state
    initial_state: OrchestratorState = {
        "message": message,
        "session_id": session_id,
        "history": history,
        "agent_id": agent_id,
        "user_access_level": user_access_level,
        "context": [],
        "mcp_triggered": False,
        "mcp_result": None,
        "response": "",
        "agent_used": None,
        "error": None
    }
    
    # Create and run graph
    graph = create_graph(db)
    result = await graph.ainvoke(initial_state)
    
    return {
        "response": result.get("response", "Error processing message"),
        "agent_used": result.get("agent_used")
    }


# ==================== New Supervisor-based Runner ====================

async def run_orchestrator_v2(
    message: str,
    session_id: str,
    history: List[Dict[str, str]],
    agent_id: Optional[str],
    db: AsyncSession,
    user_access_level: str = "normal",
    context_data: Optional[Dict[str, Any]] = None,
    monitor: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Run the new supervisor-based orchestrator (v2).
    Uses LangGraph Supervisor pattern with better LangSmith tracing.
    """
    from app.orchestrator.supervisor import run_supervisor
    return await run_supervisor(
        message=message,
        session_id=session_id,
        history=history,
        agent_id=agent_id,
        db=db,
        user_access_level=user_access_level,
        context_data=context_data,
        monitor=monitor
    )
