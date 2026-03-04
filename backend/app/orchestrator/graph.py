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
            .options(selectinload(Agent.mcps))
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
            .options(selectinload(Agent.mcps))
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
            "collaboration_enabled": agent.collaboration_enabled
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
        mcp_names = [m.name for m in agent.mcps] if agent.mcps else []
        desc = f"""
AGENTE: {agent.name}
ID: {agent.id}
DESCRIÇÃO: {agent.description or 'Sem descrição'}
ESPECIALIDADE: {agent.system_prompt[:200]}...
MCPs: {', '.join(mcp_names) if mcp_names else 'Nenhum'}
"""
        agent_descriptions.append(desc)
    
    agents_str = "\n---\n".join(agent_descriptions)
    
    selector_prompt = f"""Você é um roteador de mensagens. Analise a mensagem e escolha o agente mais adequado.

MENSAGEM: "{message}"

AGENTES DISPONÍVEIS:
{agents_str}

REGRAS:
1. Escolha o agente cuja especialidade mais se relaciona com a pergunta
2. Se nenhum for claramente adequado, retorne "NENHUM"

Responda APENAS com o ID do agente ou "NENHUM" (sem aspas, sem explicações).
"""
    
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
            if msg.get("role") == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg.get("role") == "assistant":
                from langchain_core.messages import AIMessage
                messages.append(AIMessage(content=msg["content"]))
        
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
        
        # Generate response with or without tools
        if tools:
            # Use ReAct agent with tools
            try:
                # Add system message to the messages list
                tool_instructions = "\n\nVocê tem acesso a ferramentas externas. USE-AS ATIVAMENTE quando o usuário pedir ações como agendamentos, consultas, etc. Sempre responda no mesmo idioma do usuário."
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
    context_data: Optional[Dict[str, Any]] = None
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
        context_data=context_data
    )
