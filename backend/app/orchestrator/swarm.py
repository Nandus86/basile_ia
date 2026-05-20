import logging
import re
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from langgraph.prebuilt import create_react_agent
from langgraph_swarm import create_handoff_tool, create_swarm
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

from app.orchestrator.agent_factory import AgentFactory
from app.orchestrator.agent_orchestrator import AgentOrchestrator
from app.models.agent import Agent, CollaborationStatus, AccessLevel
from app.worker.tasks import _build_workflow_tools

logger = logging.getLogger(__name__)

def sanitize_name(name: str) -> str:
    """Sanitizes agent names to be safe snake_case for LangGraph and tool requirements."""
    safe_name = name.lower()
    safe_name = re.sub(r'[^a-z0-9_]', '_', safe_name)
    safe_name = re.sub(r'_+', '_', safe_name).strip('_')
    if not safe_name:
        safe_name = "agent"
    return safe_name

async def run_swarm(
    agent_config: Dict[str, Any],
    message: str,
    session_id: str,
    history: List[Any],
    db: AsyncSession,
    context_data: Optional[Dict[str, Any]] = None,
    user_access_level: str = "normal",
) -> Dict[str, Any]:
    """
    🐝 LangGraph Swarm Orchestration Engine
    
    Compiles all collaborators (and the primary orchestrator) into a stateful,
    descentralized agent swarm. Direct handoffs are registered as tools.
    """
    agent_model = agent_config.get("agent_model")
    if not agent_model:
        raise ValueError("agent_model not found in agent_config")
        
    logger.info(f"[Swarm] 🐝 Initializing swarm for orchestrator '{agent_model.name}'")
    
    # 1. Retrieve all collaborator agents
    orchestrator_service = AgentOrchestrator(db)
    agent_with_settings = await orchestrator_service.get_agent_with_collaborators(agent_model.id)
    
    collaborators = []
    if agent_with_settings and agent_with_settings.collaborator_settings:
        for setting in agent_with_settings.collaborator_settings:
            # Skip BLOCKED collaborator settings
            if setting.status != CollaborationStatus.BLOCKED:
                collaborators.append(setting.collaborator)
                
    # Filter collaborators by vertical access level hierarchy
    try:
        user_level = AccessLevel(user_access_level)
    except ValueError:
        user_level = AccessLevel.NORMAL

    collaborators = [
        c for c in collaborators
        if user_level.can_access(c.access_level)
    ]
    
    # Swarm members include orchestrator + filtered collaborators
    swarm_members = [agent_model] + collaborators
    logger.info(f"[Swarm] Total members in swarm: {len(swarm_members)} (Orchestrator + {len(collaborators)} Collaborators)")
    
    # Generate unique, sanitized snake_case names for each member
    member_names = {}
    for member in swarm_members:
        sanitized = sanitize_name(member.name)
        original = sanitized
        counter = 1
        while sanitized in member_names.values():
            sanitized = f"{original}_{counter}"
            counter += 1
        member_names[member.id] = sanitized
        logger.info(f"[Swarm] Member mapping: '{member.name}' -> name in swarm: '{sanitized}'")
        
    # Map sanitized name to original name
    sanitized_to_original = {member_names[m.id]: m.name for m in swarm_members}
    
    # Build the capability map so all swarm members know about each other
    swarm_map_lines = []
    for member in swarm_members:
        name_in_swarm = member_names[member.id]
        desc = member.description or "Especialista"
        swarm_map_lines.append(f"- **{name_in_swarm}**: {desc}")
    swarm_map_text = "\n".join(swarm_map_lines)
    
    swarm_instructions = (
        f"\n\n## 🐝 REGRAS DO SWARM (ENXAME DE AGENTES)\n"
        f"Você faz parte de um enxame de agentes colaborativos. Caso o usuário solicite "
        f"uma tarefa fora de sua especialidade ou que outro agente listado abaixo possa "
        f"resolver melhor, você **DEVE** transferir a conversa para ele usando a ferramenta "
        f"de transferência correspondente (ex: `transfer_to_<nome_do_agente>`).\n"
        f"NÃO tente imitar ou responder pelo outro agente; use a ferramenta de transferência e deixe que ele responda.\n\n"
        f"Agentes ativos no Swarm:\n{swarm_map_text}\n"
    )
    
    factory = AgentFactory(db)
    compiled_agents = []
    
    for member in swarm_members:
        member_name = member_names[member.id]
        
        # Get configuration details
        member_config = await factory.get_agent_config(member, context_data)
        
        if member.id == agent_model.id:
            # For the main orchestrator, preserve its fully enriched prompt (RAG/Tz/Context)
            system_prompt = agent_config.get("system_prompt", "") + swarm_instructions
            member_tools = agent_config.get("tools", []) or []
            model = agent_config.get("model", "gpt-4o-mini")
            temperature = float(agent_config.get("temperature", 0.7))
            max_tokens = int(agent_config.get("max_tokens", 2000))
            provider = agent_config.get("provider")
            resilience = agent_config.get("resilience", {})
            config_dict = agent_config.get("config", {})
        else:
            # For collaborators, load prompt + tools + workspace workflows
            system_prompt = member_config.get("system_prompt", "") + swarm_instructions
            member_tools = member_config.get("tools", []) or []
            
            # Retrieve linked workflows as tools
            wf_tools = await _build_workflow_tools(db, member, context_data)
            if wf_tools:
                member_tools = list(member_tools) + wf_tools
                
            # Retrieve information bases (Weaviate search tools)
            try:
                from app.worker.tasks import _build_information_base_tools
                ib_tools = await _build_information_base_tools(db, member.id, context_data)
                if ib_tools:
                    member_tools = list(member_tools) + ib_tools
            except Exception as ib_err:
                logger.warning(f"[Swarm] Failed to load IB tools for collaborator '{member.name}': {ib_err}")
                
            model = member_config.get("model", "gpt-4o-mini")
            temperature = float(member_config.get("temperature", 0.7))
            max_tokens = int(member_config.get("max_tokens", 2000))
            provider = member_config.get("provider")
            resilience = member_config.get("resilience", {})
            config_dict = member_config.get("config", {})
            
        # Build handoff tools to all OTHER swarm members
        handoff_tools = []
        for other_member in swarm_members:
            if other_member.id != member.id:
                other_name = member_names[other_member.id]
                other_desc = other_member.description or f"Especialista {other_name}"
                h_tool = create_handoff_tool(
                    agent_name=other_name,
                    description=f"Transfere o controle para {other_name}. Use se precisar de ajuda com: {other_desc}"
                )
                handoff_tools.append(h_tool)
                
        all_agent_tools = list(member_tools) + handoff_tools
        
        # Build LLM
        mini_config = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "provider": provider,
            "config": config_dict,
            "resilience": resilience,
        }
        llm = factory.create_llm(mini_config)
        
        # Create compiled ReAct agent for this node
        node_agent = create_react_agent(
            model=llm,
            tools=all_agent_tools,
            prompt=system_prompt,
            name=member_name
        )
        compiled_agents.append(node_agent)
        logger.info(f"[Swarm] Node agent '{member_name}' compiled successfully with {len(all_agent_tools)} tools.")
        
    # 2. Build multi-agent Swarm Graph
    checkpointer = InMemorySaver()
    swarm_graph = create_swarm(
        agents=compiled_agents,
        default_active_agent=member_names[agent_model.id]
    )
    
    app = swarm_graph.compile(checkpointer=checkpointer)
    logger.info("[Swarm] Swarm graph compiled successfully.")
    
    # 3. Invoke Swarm Graph with thread state persistence
    config = {"configurable": {"thread_id": session_id}}
    inputs = {"messages": history}
    
    logger.info(f"[Swarm] Invoking swarm graph thread={session_id}")
    result = await app.ainvoke(inputs, config=config)
    
    messages_output = result.get("messages", [])
    active_agent = result.get("active_agent")
    
    # Retrieve final text response
    final_response = ""
    for msg in reversed(messages_output):
        if isinstance(msg, AIMessage) and msg.content:
            final_response = msg.content
            break
            
    # Resolve the original agent name that answered
    original_agent_name = sanitized_to_original.get(active_agent, agent_model.name)
    logger.info(f"[Swarm] Completed turn. Active Agent: '{active_agent}' ({original_agent_name})")
    
    # 4. Update session continuity context in Redis
    try:
        from app.services.redis_client import get_redis_client
        redis_client = get_redis_client()
        session_context = await redis_client.get_session_context(session_id) or {}
        agents_used = set(session_context.get("agents_used", []))
        agents_used.add(original_agent_name)
        
        await redis_client.update_session_context(
            session_id,
            last_agent_name=original_agent_name,
            agents_used=list(agents_used)
        )
        logger.info(f"[Swarm] Updated session context in Redis: last_agent='{original_agent_name}', agents_used={list(agents_used)}")
    except Exception as redis_err:
        logger.warning(f"[Swarm] Failed to update session context: {redis_err}")
        
    return {
        "response": final_response,
        "agent_used": original_agent_name
    }
