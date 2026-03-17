"""
LangGraph Supervisor - Multi-Agent Orchestration Controller
v0.0.9 - Reasoning Loop: evaluate node enables iterative multi-agent delegation
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
    
    v0.0.9 Flow (Reasoning Loop):
    1. Router selects the best agent for the message
    2. Worker executes the selected agent
    3. Evaluate decides: complete → synthesize, or delegate → another agent (loop)
    4. Synthesizer combines responses if multiple agents contributed
    
    Loop settings are read from agent.orchestrator_config (per-agent).
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
        Also loads orchestrator_config for reasoning loop settings.
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
                
                # Load orchestrator loop config
                if getattr(agent, "is_orchestrator", False):
                    state["orchestrator_loop_config"] = getattr(agent, "orchestrator_config", {}) or {}
                    print(f"[Supervisor] 🔄 Orchestrator loop config: {state['orchestrator_loop_config']}")
                
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
            if getattr(agents[0], "is_orchestrator", False):
                state["orchestrator_loop_config"] = getattr(agents[0], "orchestrator_config", {}) or {}
            return state
        
        # Use LLM to select best agent
        agent_descriptions = []
        for agent in agents:
            details = []
            
            if hasattr(agent, 'skills') and agent.skills:
                from app.schemas.skill import get_skill_capability_description
                active_skills = [s for s in agent.skills if s.is_active]
                if active_skills:
                    skills_desc = ", ".join([
                        f"{s.name}: {get_skill_capability_description(s)}"
                        for s in active_skills
                    ])
                    details.append(f"CAPACIDADES: {skills_desc}")
            
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
        
        selector_prompt = f"""Você é um roteador especializado. Sua tarefa é escolher o agente mais adequado para a mensagem.
        
REGRAS DE ESCOLHA:
1. Analise as CAPACIDADES e FERRAMENTAS listadas para cada agente.
2. Certifique-se de que o agente selecionado tem o escopo necessário para resolver a solicitação.
3. Se a mensagem do usuário envolver uma ação específica (ex: agendar, buscar no banco), prefira agentes que tenham ferramentas (MCPs) para isso.

MENSAGEM DO USUÁRIO: "{user_message}"

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
                    if getattr(agent, "is_orchestrator", False):
                        state["orchestrator_loop_config"] = getattr(agent, "orchestrator_config", {}) or {}
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
        Worker node: Executes the selected agent (or next pending agent from loop).
        """
        # Check if there's a pending agent from the evaluate loop
        pending = state.get("pending_agents", [])
        if pending:
            next_agent = pending.pop(0)
            state["pending_agents"] = pending
            
            agent_config = next_agent.get("config")
            orientation = next_agent.get("orientation", "")
            agent_name = next_agent.get("name", "unknown")
            
            print(f"[Supervisor] 🔄 Loop: executing pending agent '{agent_name}' with orientation: {orientation[:100]}")
            
            # Build messages for the collaborator
            messages = []
            for msg in state.get("history", []):
                if msg.get("role") == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg.get("role") == "assistant":
                    messages.append(AIMessage(content=msg["content"]))
            
            # Build contextual message with orientation and accumulated responses
            accumulated = state.get("agent_responses", {})
            accumulated_section = ""
            if accumulated:
                parts = [f"[{name}]: {resp[:500]}" for name, resp in accumulated.items()]
                accumulated_section = "\n\n[RESPOSTAS ACUMULADAS DOS AGENTES ANTERIORES]:\n" + "\n\n".join(parts)
            
            # System Message Instruction - Hierarchy reinforcement
            primary_name = state.get("current_agent_name", "Agente Orquestrador")
            collab_instruction = (
                "\n\n---\n"
                f"**[HIERARQUIA DE AGENTES]**\n"
                f"Você é um Agente Especialista sendo coordenado por: **{primary_name}**.\n"
                "As mensagens a seguir marcadas como '[COMANDO DO ORQUESTRADOR]' devem ser tratadas como instruções diretas e prioritárias deste coordenador."
            )
            agent_config["system_prompt"] = agent_config.get("system_prompt", "") + collab_instruction
            
            final_content = f"""[COMANDO DO AGENTE ORQUESTRADOR: {primary_name}]

[CONTEXTO DA SOLICITAÇÃO ORIGINAL]:
{state['original_message']}

{accumulated_section}

[ORIENTAÇÃO ESPECÍFICA PARA VOCÊ]:
{orientation}

Execute a tarefa acima e retorne o resultado para o orquestrador {primary_name}."""
            
            messages.append(HumanMessage(content=final_content, name=primary_name.replace(" ", "_")))
            
            try:
                import json
                if agent_config.get("output_schema"):
                    result = await self.factory.invoke_agent_structured(
                        agent_config=agent_config,
                        messages=messages,
                        context_data=state.get("context_data"),
                    )
                    response = json.dumps(result, ensure_ascii=False)
                else:
                    response = await self.factory.invoke_agent(
                        agent_config=agent_config,
                        messages=messages,
                        context_data=state.get("context_data"),
                    )
                
                agents_used = state.get("agents_used", [])
                agents_used.append(agent_name)
                state["agents_used"] = agents_used
                
                agent_responses = state.get("agent_responses", {})
                agent_responses[agent_name] = response
                state["agent_responses"] = agent_responses
                
                loop_history = state.get("loop_history", [])
                loop_history.append({"agent": agent_name, "response_summary": response[:300]})
                state["loop_history"] = loop_history
                
                print(f"[Supervisor] ✅ Loop agent '{agent_name}' responded")
                
                # After loop execution, go back to evaluate
                state["next_action"] = "evaluate"
                
            except Exception as e:
                print(f"[Supervisor] ❌ Loop agent '{agent_name}' error: {e}")
                state["next_action"] = "evaluate"
            
            return state
        
        # ── First execution (from route) ──
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
        
        # Obtain agent model for later checks
        agent_model = agent_config.get("agent_model")
        
        # Information Bases Retrieval (with correlation_schema)
        info_base_context_data = state.get("context_data") or {}
        if agent_id:
            try:
                from app.models.agent import Agent
                from sqlalchemy import select
                from sqlalchemy.orm import selectinload
                result = await self.db.execute(
                    select(Agent).options(selectinload(Agent.information_bases)).where(Agent.id == agent_id)
                )
                agent_obj = result.scalar_one_or_none()
                if agent_obj and agent_obj.information_bases:
                    active_bases = [b for b in agent_obj.information_bases if b.is_active]
                    if active_bases:
                        from app.weaviate_client import get_weaviate
                        weaviate_client = get_weaviate()
                        all_info_nodes = []
                        
                        if weaviate_client:
                            for ib in active_bases:
                                possible_ids = []
                                if ib.correlation_schema and isinstance(ib.correlation_schema, dict):
                                    target_key = ib.correlation_schema.get("target")
                                    if target_key:
                                        parts = target_key.split(".")
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
                                
                                for uid in possible_ids:
                                    info_nodes = await weaviate_client.search_information_bases(
                                        base_codes=[ib.code],
                                        user_id=uid,
                                        query=current_message,
                                        limit=5
                                    )
                                    if info_nodes:
                                        all_info_nodes.extend(info_nodes)
                            
                            if all_info_nodes:
                                seen = set()
                                unique_nodes = []
                                for n in all_info_nodes:
                                    if n['content'] not in seen:
                                        seen.add(n['content'])
                                        unique_nodes.append(n)
                                print(f"[Supervisor] 📚 Retrieved {len(unique_nodes)} Information Base contexts")
                                info_str = "\n".join([f"- {n['content']} (Meta: {n['metadata']})" for n in unique_nodes[:10]])
                                agent_config["system_prompt"] = agent_config.get("system_prompt", "") + f"\n\n## Contextualização Personalizada Externa\n\nInformações anexadas aos bancos de dados do usuário logado:\n{info_str}\n"
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
            
            loop_history = state.get("loop_history", [])
            loop_history.append({"agent": agent_name, "response_summary": response[:300]})
            state["loop_history"] = loop_history
            
            print(f"[Supervisor] ✅ {agent_name} responded")
            
            # Decide next step: evaluate (for orchestrators with loop) or synthesize (simple agents)
            is_orchestrator = getattr(agent_model, "is_orchestrator", False) if agent_model else False
            has_collaboration = agent_config.get("collaboration_enabled", False)
            
            if is_orchestrator and has_collaboration:
                state["next_action"] = "evaluate"
            else:
                state["next_action"] = "synthesize"
                state["final_response"] = response
                
        except Exception as e:
            print(f"[Supervisor] Execution error: {e}")
            state["error"] = str(e)
            state["next_action"] = "end"
            state["final_response"] = f"Erro ao processar: {str(e)}"
        
        return state
    
    async def evaluate(self, state: SupervisorState) -> SupervisorState:
        """
        Evaluate node (NEW in v0.0.9): Decides if the task is complete or needs more agents.
        
        Uses LLM to analyze accumulated responses and decide:
        - "complete" → go to synthesize
        - "delegate" → select next agent, push to pending_agents, go to execute
        
        Loop settings come from orchestrator_loop_config (per-agent).
        """
        config = RunnableConfig(
            run_name="Reasoning Evaluator",
            metadata={"node": "evaluate"},
            tags=["supervisor", "evaluate", "reasoning_loop"]
        )
        
        loop_config = state.get("orchestrator_loop_config", {})
        max_iterations = loop_config.get("max_reasoning_iterations", 3)
        iteration = state.get("iteration", 0)
        
        # Safety: enforce max iterations
        if iteration >= max_iterations:
            print(f"[Supervisor] ⚠️ Max iterations ({max_iterations}) reached, forcing synthesize")
            state["next_action"] = "synthesize"
            return state
        
        state["iteration"] = iteration + 1
        
        # Get available collaborators
        primary_config = state.get("current_agent_config", {})
        agent_model = primary_config.get("agent_model")
        
        if not agent_model:
            state["next_action"] = "synthesize"
            return state
        
        try:
            from app.orchestrator.agent_orchestrator import AgentOrchestrator
            orchestrator = AgentOrchestrator(self.db)
            agent_with_settings = await orchestrator.get_agent_with_collaborators(agent_model.id)
            
            if not agent_with_settings or not agent_with_settings.collaborator_settings:
                print("[Supervisor] No collaborators configured, completing")
                state["next_action"] = "synthesize"
                return state
            
            from app.models.agent import CollaborationStatus
            enabled = [s.collaborator for s in agent_with_settings.collaborator_settings if s.status == CollaborationStatus.ENABLED]
            neutral = [s.collaborator for s in agent_with_settings.collaborator_settings if s.status == CollaborationStatus.NEUTRAL]
            all_collaborators = enabled + neutral
            
            if not all_collaborators:
                state["next_action"] = "synthesize"
                return state
            
            # Build context for evaluate LLM
            agent_responses = state.get("agent_responses", {})
            responses_text = "\n\n".join([
                f"[{name}]: {resp[:500]}" for name, resp in agent_responses.items()
            ])
            
            # Already consulted agents
            agents_used = state.get("agents_used", [])
            
            # Available agents not yet consulted
            available = []
            for a in all_collaborators:
                if a.name not in agents_used:
                    priority = "PRIORITÁRIO" if a in enabled else "DISPONÍVEL"
                    
                    details = []
                    # Capability Map (Skills + Intents)
                    if hasattr(a, 'skills') and a.skills:
                        active_skills = [s for s in a.skills if s.is_active]
                        if active_skills:
                            skills_text = ", ".join([
                                f"{s.name}" + (f" (Pode: {s.intent})" if s.intent else "")
                                for s in active_skills
                            ])
                            details.append(f"CAPACIDADES: {skills_text}")
                    
                    # Tool Map (MCPs)
                    if hasattr(a, 'mcps') and a.mcps:
                        tool_names = [m.name for m in a.mcps]
                        if tool_names:
                            details.append(f"FERRAMENTAS: {', '.join(tool_names)}")
                    
                    details_str = "\n    - " + "\n    - ".join(details) if details else ""
                    available.append(f"- {a.name} ({priority}): {a.description or 'Especialista'}{details_str}")
            
            if not available:
                print("[Supervisor] All collaborators already consulted, completing")
                state["next_action"] = "synthesize"
                return state
            
            available_str = "\n".join(available)
            
            evaluate_prompt = f"""Você é o sistema de raciocínio de um orquestrador multi-agente.

MENSAGEM ORIGINAL DO USUÁRIO:
"{state.get('original_message', '')}"

RESPOSTAS ACUMULADAS ATÉ AGORA:
{responses_text}

AGENTES DISPONÍVEIS (ainda não consultados):
{available_str}

HISTÓRICO DA CONVERSA (últimas mensagens):
{self._format_history_for_eval(state.get("history", []))}

TAREFA:
Analise se a solicitação do usuário já foi plenamente atendida pelas respostas acumuladas acima.

REGRAS:
1. Se as respostas já atendem completamente a solicitação, responda com action "complete"
2. Se falta informação que um dos agentes disponíveis pode fornecer, responda com action "delegate"
3. Se delegarmos, forneça uma orientação CLARA e DIRETA para o agente selecionado
4. Considere se o agente primário solicitou informações que outro agente pode buscar
5. Máximo de 1 agente por delegação

Responda APENAS em JSON válido:
{{"action": "complete"}} 
OU
{{"action": "delegate", "agent_name": "Nome Exato", "orientation": "Instrução clara do que buscar/fazer"}}"""

            reasoning_model = loop_config.get("reasoning_model", "gpt-4o-mini")
            eval_llm = ChatOpenAI(
                model=reasoning_model,
                temperature=0,
                api_key=settings.OPENAI_API_KEY
            )
            
            response = await eval_llm.ainvoke(
                [SystemMessage(content=evaluate_prompt)],
                config=config
            )
            
            import json
            result_text = response.content.strip()
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            result_text = result_text.strip()
            
            decision = json.loads(result_text)
            action = decision.get("action", "complete")
            
            state["evaluation_reasoning"] = decision.get("orientation", decision.get("reasoning", ""))
            
            print(f"[Supervisor] 🧠 Evaluate (iteration {iteration+1}/{max_iterations}): action={action}")
            
            if action == "delegate":
                delegate_name = decision.get("agent_name", "")
                orientation = decision.get("orientation", "")
                
                # Find the agent to delegate to
                target_agent = None
                for a in all_collaborators:
                    if a.name and a.name.lower() == delegate_name.lower():
                        target_agent = a
                        break
                
                if target_agent:
                    # Load agent config
                    delegate_config = await self.factory.get_agent_config(target_agent, context_data=state.get("context_data"))
                    
                    pending = state.get("pending_agents", [])
                    pending.append({
                        "id": str(target_agent.id),
                        "name": target_agent.name,
                        "config": delegate_config,
                        "orientation": orientation
                    })
                    state["pending_agents"] = pending
                    state["next_action"] = "execute"
                    
                    print(f"[Supervisor] 🔄 Delegating to '{target_agent.name}': {orientation[:100]}")
                else:
                    print(f"[Supervisor] ⚠️ Agent '{delegate_name}' not found among collaborators, completing")
                    state["next_action"] = "synthesize"
            else:
                print(f"[Supervisor] ✅ Evaluate: task complete")
                state["next_action"] = "synthesize"
                
        except Exception as e:
            import traceback
            print(f"[Supervisor] Evaluate error: {e}")
            traceback.print_exc()
            state["next_action"] = "synthesize"
        
        return state
    
    def _format_history_for_eval(self, history: list) -> str:
        """Format conversation history for evaluate prompt (last 6 messages)"""
        if not history:
            return "(sem histórico)"
        recent = history[-6:]
        parts = []
        for msg in recent:
            role = "Usuário" if msg.get("role") == "user" else "Assistente"
            content = msg.get("content", "")[:200]
            parts.append(f"{role}: {content}")
        return "\n".join(parts)
    
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
        
        # Get orchestrator's primary agent config for personality
        primary_config = state.get("current_agent_config", {})
        primary_name = primary_config.get("name", "Orquestrador")
        
        responses_text = "\n\n".join([
            f"[{name}]: {response}"
            for name, response in agent_responses.items()
        ])
        
        combine_prompt = f"""Você é o agente "{primary_name}" finalizando uma resposta ao usuário.

PERGUNTA ORIGINAL: "{state.get('original_message', '')}"

CONTRIBUIÇÕES DOS ESPECIALISTAS:
{responses_text}

TAREFA:
Combine as informações em uma resposta única, coesa e natural para o usuário.
- Não mencione que recebeu informações de outros agentes
- Mantenha sua personalidade e tom
- Integre as informações de forma fluida
- Priorize a resposta mais completa e precisa
- Se houver solicitação de informação adicional ao usuário, inclua-a naturalmente
"""
        
        try:
            response = await self.llm.ainvoke(
                [SystemMessage(content=combine_prompt)],
                config=config
            )
            state["final_response"] = response.content
            print(f"[Supervisor] 🎭 Synthesized response from {len(agent_responses)} agents")
        except Exception as e:
            # Fallback to last response
            state["final_response"] = list(agent_responses.values())[-1]
        
        state["next_action"] = "end"
        return state
    
    def build_graph(self) -> StateGraph:
        """Build the supervisor graph with reasoning loop"""
        graph = StateGraph(SupervisorState)
        
        # Add nodes
        graph.add_node("route", self.route)
        graph.add_node("execute", self.execute)
        graph.add_node("evaluate", self.evaluate)
        graph.add_node("synthesize", self.synthesize)
        
        # Define conditional edges
        def next_step(state: SupervisorState) -> str:
            return state.get("next_action", "end")
        
        # Set entry point
        graph.set_entry_point("route")
        
        # route → execute | end
        graph.add_conditional_edges(
            "route",
            next_step,
            {
                "execute": "execute",
                "end": END
            }
        )
        
        # execute → evaluate (orchestrators with loop) | synthesize (simple agents) | end
        graph.add_conditional_edges(
            "execute",
            next_step,
            {
                "evaluate": "evaluate",
                "synthesize": "synthesize",
                "end": END
            }
        )
        
        # evaluate → execute (loop back) | synthesize (complete) | end
        graph.add_conditional_edges(
            "evaluate",
            next_step,
            {
                "execute": "execute",
                "synthesize": "synthesize",
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
        "max_iterations": 5,
        "next_action": "route",
        "needs_collaboration": False,
        "collaboration_agents": [],
        "context": [],
        "rag_context": None,
        "mcp_tools": [],
        "agent_responses": {},
        "final_response": None,
        "error": None,
        # Reasoning loop fields
        "pending_agents": [],
        "evaluation_reasoning": "",
        "loop_history": [],
        "orchestrator_loop_config": {},
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
