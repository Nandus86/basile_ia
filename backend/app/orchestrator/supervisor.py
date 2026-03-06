"""
LangGraph Supervisor - Multi-Agent Orchestration Controller
"""
from typing import List, Optional, Dict, Any, Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from sqlalchemy.ext.asyncio import AsyncSession

from app.orchestrator.state import SupervisorState
from app.orchestrator.agent_factory import AgentFactory
from app.config import settings


class Supervisor:
    """
    LangGraph-based Supervisor that orchestrates multiple agents.
    
    Flow:
    1. Router selects the best agent for the message
    2. Worker executes the selected agent
    3. Supervisor decides if collaboration is needed
    4. Synthesizer combines responses if multiple agents contributed
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.factory = AgentFactory(db)
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            api_key=settings.OPENAI_API_KEY
        )
    
    async def route(self, state: SupervisorState) -> SupervisorState:
        """
        Router node: Selects the best agent for the message.
        Traced as 'Agent Router' in LangSmith.
        """
        config = RunnableConfig(
            run_name="Agent Router",
            metadata={"node": "router"},
            tags=["supervisor", "routing"]
        )
        
        user_message = state.get("original_message", "")
        requested_agent_id = state.get("requested_agent_id")
        user_access_level = state.get("user_access_level", "normal")
        
        # If specific agent requested
        if requested_agent_id:
            agent = await self.factory.get_agent_by_id(requested_agent_id)
            if agent:
                agent_config = await self.factory.get_agent_config(agent, context_data=state.get("context_data"))
                state["current_agent_id"] = agent_config["id"]
                state["current_agent_name"] = agent_config["name"]
                state["current_agent_config"] = agent_config
                state["next_action"] = "execute"
                state["vector_memory_enabled"] = getattr(agent, "vector_memory_enabled", False)
                print(f"[Supervisor] Direct route to: {agent_config['name']}")
                return state
        
        # Get all accessible agents
        agents = await self.factory.get_accessible_agents(user_access_level)
        
        if not agents:
            state["next_action"] = "end"
            state["final_response"] = "Nenhum agente disponível para seu nível de acesso."
            return state
        
        if len(agents) == 1:
            agent_config = await self.factory.get_agent_config(agents[0], context_data=state.get("context_data"))
            state["current_agent_id"] = agent_config["id"]
            state["current_agent_name"] = agent_config["name"]
            state["current_agent_config"] = agent_config
            state["next_action"] = "execute"
            state["vector_memory_enabled"] = getattr(agents[0], "vector_memory_enabled", False)
            return state
        
        # Use LLM to select best agent
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
        
        selector_prompt = f"""Você é um roteador. Escolha o agente mais adequado para a mensagem.

MENSAGEM: "{user_message}"

AGENTES DISPONÍVEIS:
{agents_str}

Responda APENAS com o ID do agente (UUID). Sem explicações."""
        
        try:
            response = await self.llm.ainvoke(
                [SystemMessage(content=selector_prompt)],
                config=config
            )
            selected_id = response.content.strip()
            
            # Find matching agent
            for agent in agents:
                if str(agent.id) == selected_id:
                    agent_config = await self.factory.get_agent_config(agent, context_data=state.get("context_data"))
                    state["current_agent_id"] = agent_config["id"]
                    state["current_agent_name"] = agent_config["name"]
                    state["current_agent_config"] = agent_config
                    state["next_action"] = "execute"
                    state["vector_memory_enabled"] = getattr(agent, "vector_memory_enabled", False)
                    print(f"[Supervisor] LLM selected: {agent_config['name']}")
                    return state
            
            # Fallback to first agent
            agent_config = await self.factory.get_agent_config(agents[0], context_data=state.get("context_data"))
            state["current_agent_id"] = agent_config["id"]
            state["current_agent_name"] = agent_config["name"]
            state["current_agent_config"] = agent_config
            state["next_action"] = "execute"
            state["vector_memory_enabled"] = getattr(agents[0], "vector_memory_enabled", False)
            
        except Exception as e:
            print(f"[Supervisor] Router error: {e}")
            agent_config = await self.factory.get_agent_config(agents[0], context_data=state.get("context_data"))
            state["current_agent_id"] = agent_config["id"]
            state["current_agent_name"] = agent_config["name"]
            state["current_agent_config"] = agent_config
            state["next_action"] = "execute"
            state["vector_memory_enabled"] = getattr(agents[0], "vector_memory_enabled", False)
        
        return state
    
    async def execute(self, state: SupervisorState) -> SupervisorState:
        """
        Worker node: Executes the selected agent.
        Traced as 'Agent: {name}' in LangSmith.
        """
        agent_config = state.get("current_agent_config")
        if not agent_config:
            state["next_action"] = "end"
            state["final_response"] = "Erro: Nenhum agente selecionado."
            return state
        
        agent_name = agent_config["name"]
        agent_id = agent_config["id"]
        
        # Get RAG context if available
        rag_context = None
        try:
            from app.services.rag_service import get_rag_context
            rag_context = await get_rag_context(
                self.db, agent_id, state["original_message"], limit=5
            )
            if rag_context:
                print(f"[Supervisor] 📚 RAG context loaded for {agent_name}")
        except Exception as e:
            print(f"[Supervisor] RAG error: {e}")
            
        vector_memory_enabled = state.get("vector_memory_enabled", False)
        contact_id = state.get("session_id")
        current_message = state["original_message"]
        
        # Information Bases Retrieval
        info_base_context_data = state.get("context_data") or {}
        print(f"[Supervisor] 🔍 INFO_BASE DEBUG: agent_id={agent_id}, context_data={info_base_context_data}")
        if agent_id:
            try:
                from app.models.agent import Agent
                from sqlalchemy import select
                from sqlalchemy.orm import selectinload
                result = await self.db.execute(
                    select(Agent).options(selectinload(Agent.information_bases)).where(Agent.id == agent_id)
                )
                agent_obj = result.scalar_one_or_none()
                print(f"[Supervisor] 🔍 INFO_BASE DEBUG: agent_obj={agent_obj}, has_bases={bool(agent_obj and agent_obj.information_bases)}")
                if agent_obj and agent_obj.information_bases:
                    print(f"[Supervisor] 🔍 INFO_BASE DEBUG: bases={[(b.code, b.is_active) for b in agent_obj.information_bases]}")
                    base_codes = [b.code for b in agent_obj.information_bases if b.is_active]
                    print(f"[Supervisor] 🔍 INFO_BASE DEBUG: active base_codes={base_codes}")
                    if base_codes:
                        # Collect all possible user IDs from context_data values
                        possible_ids = []
                        for v in info_base_context_data.values():
                            if isinstance(v, str) and v.strip():
                                possible_ids.append(v.strip())
                        # Also try session_id as fallback
                        if contact_id:
                            possible_ids.append(str(contact_id))
                        print(f"[Supervisor] 🔍 INFO_BASE DEBUG: possible_ids={possible_ids}")
                        
                        from app.weaviate_client import get_weaviate
                        weaviate_client = get_weaviate()
                        print(f"[Supervisor] 🔍 INFO_BASE DEBUG: weaviate_client={weaviate_client}")
                        if weaviate_client and possible_ids:
                            all_info_nodes = []
                            for uid in possible_ids:
                                print(f"[Supervisor] 🔍 INFO_BASE DEBUG: searching base_codes={base_codes}, user_id={uid}, query={current_message}")
                                info_nodes = await weaviate_client.search_information_bases(
                                    base_codes=base_codes,
                                    user_id=uid,
                                    query=current_message,
                                    limit=5
                                )
                                print(f"[Supervisor] 🔍 INFO_BASE DEBUG: search returned {len(info_nodes)} nodes for uid={uid}")
                                if info_nodes:
                                    all_info_nodes.extend(info_nodes)
                            print(f"[Supervisor] 🔍 INFO_BASE DEBUG: total all_info_nodes={len(all_info_nodes)}")
                            if all_info_nodes:
                                # Deduplicate by content
                                seen = set()
                                unique_nodes = []
                                for n in all_info_nodes:
                                    if n['content'] not in seen:
                                        seen.add(n['content'])
                                        unique_nodes.append(n)
                                print(f"[Supervisor] 📚 Retrieved {len(unique_nodes)} Information Base contexts")
                                info_str = "\n".join([f"- {n['content']} (Meta: {n['metadata']})" for n in unique_nodes[:10]])
                                system_addition = f"\n\n## Contextualização Personalizada Externa\n\nInformações anexadas aos bancos de dados do usuário logado:\n{info_str}\n"
                                agent_config["system_prompt"] = agent_config.get("system_prompt", "") + system_addition
                                print(f"[Supervisor] 🔍 INFO_BASE DEBUG: system_prompt updated, length={len(agent_config['system_prompt'])}")
                            else:
                                print(f"[Supervisor] 🔍 INFO_BASE DEBUG: no nodes found for any user ID")
                else:
                    print(f"[Supervisor] 🔍 INFO_BASE DEBUG: agent has no information_bases linked")
            except Exception as e:
                import traceback
                print(f"[Supervisor] Failed to retrieve Information Bases context: {e}")
                traceback.print_exc()
        
        # Vector Memory Retrieval
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
                        print(f"[Supervisor] 🧠 Retrieved {len(memories)} qualitative facts for contact {contact_id}")
                        mem_str = "\n".join([f"- {m['content']}" for m in memories])
                        
                        system_addition = f"""

## Inteligência e Memória Histórica do Contato

Abaixo estão informações e peculiaridades qualitativas deste usuário, adquiridas em interações anteriores. 
Utilize isso para personalizar ativamente o engajamento de maneira natural:

{mem_str}
"""
                        # We must inject this into the agent's system prompt before invoking
                        agent_config["system_prompt"] = agent_config.get("system_prompt", "") + system_addition
            except Exception as e:
                import traceback
                print(f"[Supervisor] Failed to retrieve vector memory: {e}")
                traceback.print_exc()

        # Extract New Vector Memories in background asynchronously
        if vector_memory_enabled and agent_id and contact_id:
            try:
                from app.services.vector_memory_service import extract_and_save_memories
                import asyncio
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
                print(f"[Supervisor] Failed to launch extraction task: {e}")
        
        # Build messages
        messages = []
        for msg in state.get("history", []):
            if msg.get("role") == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg.get("role") == "assistant":
                messages.append(AIMessage(content=msg["content"]))
        
        messages.append(HumanMessage(content=state["original_message"]))
        
        # Invoke agent
        try:
            response = await self.factory.invoke_agent(
                agent_config=agent_config,
                messages=messages,
                rag_context=rag_context,
                context_data=state.get("context_data")
            )
            
            # Store response
            agents_used = state.get("agents_used", [])
            agents_used.append(agent_name)
            state["agents_used"] = agents_used
            
            agent_responses = state.get("agent_responses", {})
            agent_responses[agent_name] = response
            state["agent_responses"] = agent_responses
            
            print(f"[Supervisor] ✅ {agent_name} responded")
            
            # Check if collaboration is needed
            if agent_config.get("collaboration_enabled", False):
                state["next_action"] = "check_collaboration"
            else:
                state["next_action"] = "synthesize"
                state["final_response"] = response
                
        except Exception as e:
            print(f"[Supervisor] Execution error: {e}")
            state["error"] = str(e)
            state["next_action"] = "end"
            state["final_response"] = f"Erro ao processar: {str(e)}"
        
        return state
    
    async def check_collaboration(self, state: SupervisorState) -> SupervisorState:
        """
        Check if the current agent needs to collaborate with others.
        """
        config = RunnableConfig(
            run_name="Collaboration Check",
            metadata={"node": "collaboration"},
            tags=["supervisor", "collaboration"]
        )
        
        agent_config = state.get("current_agent_config")
        current_response = state.get("agent_responses", {}).get(agent_config["name"], "")
        iteration = state.get("iteration", 0)
        max_iterations = state.get("max_iterations", 3)
        
        # Limit iterations
        if iteration >= max_iterations:
            state["next_action"] = "synthesize"
            return state
        
        # Check with orchestrator
        try:
            from app.orchestrator.agent_orchestrator import AgentOrchestrator
            orchestrator = AgentOrchestrator(self.db)
            
            agent_model = agent_config.get("agent_model")
            if agent_model and agent_model.collaboration_enabled:
                # Get collaboration decision
                enhanced_response = await orchestrator.orchestrate(
                    message=state["original_message"],
                    primary_agent=agent_model,
                    primary_response=current_response,
                    context=""
                )
                
                if enhanced_response != current_response:
                    print(f"[Supervisor] 🎭 Collaboration enhanced response")
                    state["agent_responses"][agent_config["name"]] = enhanced_response
                    state["final_response"] = enhanced_response
                    
        except Exception as e:
            print(f"[Supervisor] Collaboration check error: {e}")
        
        state["iteration"] = iteration + 1
        state["next_action"] = "synthesize"
        return state
    
    async def synthesize(self, state: SupervisorState) -> SupervisorState:
        """
        Synthesizer node: Combines responses if multiple agents contributed.
        """
        agent_responses = state.get("agent_responses", {})
        
        if len(agent_responses) <= 1:
            # Single agent, use its response directly
            if agent_responses:
                state["final_response"] = list(agent_responses.values())[0]
            state["next_action"] = "end"
            return state
        
        # Multiple agents, combine responses
        config = RunnableConfig(
            run_name="Response Synthesizer",
            metadata={"node": "synthesizer"},
            tags=["supervisor", "synthesis"]
        )
        
        responses_text = "\n\n".join([
            f"[{name}]: {response}"
            for name, response in agent_responses.items()
        ])
        
        combine_prompt = f"""Combine as seguintes respostas em uma única resposta coesa:

{responses_text}

REGRAS:
- Mantenha as informações mais importantes de cada resposta
- Crie uma resposta única e natural
- Não mencione que são respostas de diferentes agentes
"""
        
        try:
            response = await self.llm.ainvoke(
                [SystemMessage(content=combine_prompt)],
                config=config
            )
            state["final_response"] = response.content
        except Exception as e:
            # Fallback to first response
            state["final_response"] = list(agent_responses.values())[0]
        
        state["next_action"] = "end"
        return state
    
    def build_graph(self) -> StateGraph:
        """Build the supervisor graph"""
        graph = StateGraph(SupervisorState)
        
        # Add nodes
        graph.add_node("route", self.route)
        graph.add_node("execute", self.execute)
        graph.add_node("check_collaboration", self.check_collaboration)
        graph.add_node("synthesize", self.synthesize)
        
        # Define conditional edges
        def next_step(state: SupervisorState) -> str:
            return state.get("next_action", "end")
        
        # Set entry point
        graph.set_entry_point("route")
        
        # Add conditional edges
        graph.add_conditional_edges(
            "route",
            next_step,
            {
                "execute": "execute",
                "end": END
            }
        )
        
        graph.add_conditional_edges(
            "execute",
            next_step,
            {
                "check_collaboration": "check_collaboration",
                "synthesize": "synthesize",
                "end": END
            }
        )
        
        graph.add_conditional_edges(
            "check_collaboration",
            next_step,
            {
                "synthesize": "synthesize",
                "route": "route",  # Can redirect to another agent
                "end": END
            }
        )
        
        graph.add_edge("synthesize", END)
        
        return graph.compile()


async def run_supervisor(
    message: str,
    session_id: str,
    history: List[Dict[str, str]],
    agent_id: Optional[str],
    db: AsyncSession,
    user_access_level: str = "normal",
    context_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Run the supervisor orchestrator.
    
    Args:
        message: User message
        session_id: Session identifier
        history: Conversation history
        agent_id: Optional specific agent ID
        db: Database session
        user_access_level: User's access level
        context_data: Optional structured context data for the agent
        
    Returns:
        Dict with response and agents_used
    """
    supervisor = Supervisor(db)
    graph = supervisor.build_graph()
    
    # Create initial state
    initial_state: SupervisorState = {
        "messages": [],
        "original_message": message,
        "session_id": session_id,
        "history": history,
        "requested_agent_id": agent_id,
        "user_access_level": user_access_level,
        "context_data": context_data,
        "current_agent_id": None,
        "current_agent_name": None,
        "current_agent_config": None,
        "agents_used": [],
        "iteration": 0,
        "max_iterations": 3,
        "next_action": "route",
        "needs_collaboration": False,
        "collaboration_agents": [],
        "context": [],
        "rag_context": None,
        "mcp_tools": [],
        "agent_responses": {},
        "final_response": None,
        "error": None
    }
    
    # Run graph with LangSmith tracing
    config = RunnableConfig(
        run_name="Supervisor Orchestrator",
        metadata={
            "session_id": session_id,
            "user_access_level": user_access_level
        },
        tags=["supervisor", "orchestrator"]
    )
    
    result = await graph.ainvoke(initial_state, config=config)
    
    return {
        "response": result.get("final_response", "Erro ao processar mensagem"),
        "agent_used": ", ".join(result.get("agents_used", ["default"])),
        "agents_used": result.get("agents_used", [])
    }
