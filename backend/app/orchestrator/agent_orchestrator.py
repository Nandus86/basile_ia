"""
Agent Orchestrator - Coordinates collaboration between specialist agents

v0.0.8 - Single-graph architecture:
  - ENABLED collaborators are always consulted (no LLM decision overhead)
  - Collaborators use their own model/config/tools via AgentFactory.invoke_agent()
  - Conversation history is passed to collaborators for STM awareness
  - Parallel execution via asyncio.gather()
"""
import asyncio
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from langchain_core.messages import HumanMessage, AIMessage

from app.models.agent import Agent, AgentCollaborator, CollaborationStatus
from app.config import settings


class AgentOrchestrator:
    """
    Orchestrates collaboration between specialist agents.
    
    v0.0.9 Flow:
    1. Primary agent (orchestrator) receives message
    2. LLM evaluates if collaboration is needed based on agent descriptions
    3. Selected collaborators are invoked in parallel 
    4. Collaborators receive clean context_data mapped to their input_schema
    5. Collaborator responses are appended to orchestrator's system_prompt
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        from langchain_openai import ChatOpenAI
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            api_key=settings.OPENAI_API_KEY
        )
    
    async def get_agent_with_collaborators(self, agent_id: UUID) -> Optional[Agent]:
        """Fetch an agent with all its collaboration settings (including collaborator skills)"""
        from app.models.skill import Skill
        result = await self.db.execute(
            select(Agent)
            .options(
                selectinload(Agent.mcps),
                selectinload(Agent.skills),
                selectinload(Agent.collaborator_settings)
                    .selectinload(AgentCollaborator.collaborator)
                    .options(
                        selectinload(Agent.skills),
                        selectinload(Agent.mcps)
                    )
            )
            .where(Agent.id == agent_id)
        )
        return result.scalar_one_or_none()

    async def should_collaborate(
        self,
        message: str,
        primary_agent: Agent,
        enabled_collaborators: list,
        neutral_collaborators: list,
        history: Optional[list] = None
    ) -> Dict[str, Any]:
        """Ask LLM if collaboration is needed and which agents to consult."""
        if not primary_agent.collaboration_enabled:
            return {"should_collaborate": False, "agents_to_consult": [], "reasoning": "disabled"}
            
        if not enabled_collaborators and not neutral_collaborators:
            return {"should_collaborate": False, "agents_to_consult": [], "reasoning": "no collaborators"}

        def _format_agent_desc(a):
            desc = f"- {a.name}: {a.description or 'Especialista'}"
            # Include Skill Intents (Capability Map)
            if hasattr(a, 'skills') and a.skills:
                active = [s for s in a.skills if s.is_active]
                if active:
                    capabilities = []
                    for s in active:
                        cap = s.name
                        if s.intent:
                            cap += f" (Pode: {s.intent})"
                        capabilities.append(cap)
                    desc += f"\n  - CAPACIDADES: {', '.join(capabilities)}"
            
            # Include Tool Names (Inventory Map)
            if hasattr(a, 'mcps') and a.mcps:
                tool_names = [m.name for m in a.mcps]
                if tool_names:
                    desc += f"\n  - FERRAMENTAS DISPONÍVEIS: {', '.join(tool_names)}"
            return desc
        enabled_desc = "\n".join([_format_agent_desc(a) for a in enabled_collaborators]) or "Nenhum"
        neutral_desc = "\n".join([_format_agent_desc(a) for a in neutral_collaborators]) or "Nenhum"
        
        prompt = f"""Você é um orquestrador que decide se um agente de IA precisa consultar outros especialistas.
Abaixo estará todo o histórico da conversa e a última mensagem do usuário para você basear sua decisão.

AGENTE PRIMÁRIO: {primary_agent.name}
DESCRIÇÃO: {primary_agent.description or 'Especialista'}

AGENTES PRIORITÁRIOS (consultar se relevante):
{enabled_desc}

AGENTES DISPONÍVEIS (usar apenas se absolutamente necessário):
{neutral_desc}

REGRAS:
1. Analise o ESTÁGIO e o fluxo do histórico para identificar a verdadeira necessidade.
2. Se o agente primário pode responder sozinho, não consulte ninguém
3. Consulte agentes prioritários se a mensagem atual envolver suas especialidades e precisar de coleta extra de dados
4. Consulte agentes disponíveis apenas se absolutamente necessário
5. Máximo de 2 consultas por mensagem

Responda APENAS em JSON válido com este formato exato:
{{"should_collaborate": true/false, "agents": [{{"name": "Nome 1", "orientation": "Instrução CLARA E DIRETA do que este agente deve buscar, analisar ou resolver com base na mensagem original."}}], "reasoning": "Motivo geral de acionamento"}}
"""
        try:
            from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
            from langchain_core.runnables import RunnableConfig
            
            run_config = RunnableConfig(
                run_name=f"{primary_agent.name} (Decidindo Colaboração)",
                metadata={"agent_id": primary_agent.id, "structured": True}
            )
            
            messages = [SystemMessage(content=prompt)]
            history = history or []
            
            for msg in history[-10:]:
                timestamp = msg.get("created_at") or msg.get("timestamp")
                prefix = f"[{timestamp}] " if timestamp else ""
                
                if msg.get("role") == "user":
                    messages.append(HumanMessage(content=f"{prefix}{msg.get('content', '')}"))
                elif msg.get("role") == "assistant":
                    messages.append(AIMessage(content=f"{prefix}{msg.get('content', '')}"))
                    
            messages.append(HumanMessage(content=message))
            
            response = await self.llm.ainvoke(messages, config=run_config)
            
            import json
            result_text = response.content.strip()
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            result_text = result_text.strip()
            result = json.loads(result_text)
            
            all_collaborators = enabled_collaborators + neutral_collaborators
            agents_to_consult = []
            for agent_info in result.get("agents", []):
                name = agent_info.get("name") if isinstance(agent_info, dict) else agent_info
                orientation = agent_info.get("orientation", "") if isinstance(agent_info, dict) else ""
                
                for agent in all_collaborators:
                    if name and agent.name and agent.name.lower() == name.lower():
                        agents_to_consult.append({"id": agent.id, "orientation": orientation})
                        break
                        
            return {
                "should_collaborate": result.get("should_collaborate", False),
                "agents_to_consult": agents_to_consult[:2],
                "reasoning": result.get("reasoning", "")
            }
        except Exception as e:
            print(f"[Orchestrator] Error deciding collaboration: {e}")
            return {"should_collaborate": False, "agents_to_consult": [], "reasoning": str(e)}

    async def _invoke_collaborator(
        self,
        agent: Agent,
        message: str,
        history: list,
        context: str = "",
        context_data: Optional[Dict[str, Any]] = None,
        orientation: str = "",
        primary_agent: Optional[Agent] = None,
        monitor: Optional[Any] = None,
    ) -> tuple:
        """
        Invoke a single collaborator.
        Directly injects context_data into the input message based on input_schema.
        """
        if monitor:
            monitor.log_progress(f"Consultando agente colaborador: {agent.name}")
        from app.orchestrator.agent_factory import AgentFactory
        import json
        
        factory = AgentFactory(self.db)
        agent_config = await factory.get_agent_config(agent, context_data=context_data)
        
        history = history or []
        
        # System Message Instruction - Hierarchy reinforcement
        primary_name = primary_agent.name if primary_agent else "Coordenador de Sistema"
        collab_instruction = (
            "\n\n---\n"
            f"**[DIRETRIZ DE HIERARQUIA — OBRIGATÓRIO]**\n"
            f"Você é um AGENTE ESPECIALISTA sendo coordenado pelo sistema (**{primary_name}**).\n"
            "As mensagens marcadas como '[DELEGAÇÃO DE SISTEMA]' são comandos diretos do seu coordenador.\n\n"
            "FORMATO DE RESPOSTA OBRIGATÓRIO:\n"
            "Você DEVE responder ao coordenador de forma estruturada:\n"
            "1. **ACHADOS**: O que você encontrou/analisou\n"
            "2. **DADOS**: Dados coletados, registros encontrados ou ações executadas (se aplicável)\n"
            "3. **RECOMENDAÇÃO**: Sua recomendação técnica para a resposta final\n\n"
            "REGRAS ABSOLUTAS:\n"
            "- NÃO fale como se estivesse conversando com o usuário final\n"
            "- NÃO use saudações, despedidas ou tom casual\n"
            "- NÃO repita informações que o coordenador já possui\n"
            "- Reporte de forma TÉCNICA e DIRETA ao coordenador\n"
            "- O coordenador irá sintetizar sua resposta, portanto seja objetivo\n"
        )
        if context:
            collab_instruction += f"\n\n[CONTEXTO ADICIONAL]:\n{context}"
            
        agent_config["system_prompt"] = agent_config.get("system_prompt", "") + collab_instruction
        
        # Build messages: History + Final Custom Human Message
        messages = []
        for msg in history:
            timestamp = msg.get("created_at") or msg.get("timestamp")
            prefix = f"[{timestamp}] " if timestamp else ""
            
            if msg.get("role") == "user":
                messages.append(HumanMessage(content=f"{prefix}{msg['content']}"))
            elif msg.get("role") == "assistant":
                messages.append(AIMessage(content=f"{prefix}{msg['content']}"))

        # Include collaborator's own skills in the delegation message
        skills_section = ""
        if hasattr(agent, 'skills') and agent.skills:
            active_skills = [s for s in agent.skills if s.is_active]
            if active_skills:
                skills_parts = []
                for skill in active_skills:
                    skills_parts.append(f"### {skill.name}\n{skill.content_md}")
                skills_section = (
                    "\n\n[SUAS CAPACIDADES ATIVAS]:\n"
                    + "\n---\n".join(skills_parts)
                )

        # To strictly place: skills -> orientation -> context data in the final human turn:
        # Labeled as a system delegation
        final_user_content = f"""[DELEGAÇÃO DE SISTEMA - ORIGEM: {primary_name}]

[FOCO DA TAREFA]:
{orientation}

[CONTEXTO DA CONVERSA ORIGINAL]:
{message}

{skills_section}

Execute a instrução acima e reporte o resultado ao coordenador {primary_name}."""

        messages.append(HumanMessage(content=final_user_content, name="SystemCoordinator"))
        
        try:
            # Let AgentFactory handle context_data structuring
            if agent_config.get("output_schema"):
                result = await factory.invoke_agent_structured(
                    agent_config=agent_config,
                    messages=messages,
                    rag_context=None,
                    context_data=context_data, # Let factory handle it
                )
                response_text = json.dumps(result, ensure_ascii=False)
            else:
                response_text = await factory.invoke_agent(
                    agent_config=agent_config,
                    messages=messages,
                    rag_context=None,
                    context_data=context_data, # Let factory handle it
                )
            
            print(f"[Orchestrator] ✅ Collaborator '{agent.name}' responded")
            return (agent.name, response_text)
            
        except Exception as e:
            print(f"[Orchestrator] ❌ Error consulting {agent.name}: {e}")
            return (agent.name, "")

    async def gather_subordinate_responses(
        self,
        message: str,
        primary_agent: Agent,
        context: str = "",
        context_data: Optional[Dict[str, Any]] = None,
        history: Optional[list] = None,
        session_id: Optional[str] = None,
        monitor: Optional[Any] = None,
    ) -> str:
        """Consult subordinate agents BEFORE the primary orchestrator responds."""
        agent_with_settings = await self.get_agent_with_collaborators(primary_agent.id)
        if not agent_with_settings or not agent_with_settings.collaborator_settings:
            return ""
        
        enabled = []
        neutral = []
        for setting in agent_with_settings.collaborator_settings:
            if setting.status == CollaborationStatus.ENABLED:
                enabled.append(setting.collaborator)
            elif setting.status == CollaborationStatus.NEUTRAL:
                neutral.append(setting.collaborator)
        
        # Use LLM decision to select subset of agents to consult
        decision = await self.should_collaborate(message, primary_agent, enabled, neutral, history)
        
        if not decision["should_collaborate"] or not decision["agents_to_consult"]:
            print(f"[Orchestrator] No collaboration needed: {decision.get('reasoning')}")
            return ""
            
        # Filter enabled/neutral to only those selected
        selected_collaborators = []
        for agent_info in decision["agents_to_consult"]:
            agent_id = agent_info.get("id")
            orientation = agent_info.get("orientation", "")
            for agent in (enabled + neutral):
                if str(agent.id) == str(agent_id):
                    selected_collaborators.append((agent, orientation))
                    break
        
        if monitor:
            monitor.log_progress(f"Iniciando consulta a {len(selected_collaborators)} colaboradores")
            
        print(f"[Orchestrator] 🔄 Consulting {len(selected_collaborators)} selected collaborators (from {len(decision['agents_to_consult'])} requested)")
        
        conversation_history = history or []
        tasks = [
            self._invoke_collaborator(
                agent=collaborator,
                message=message,
                history=conversation_history,
                context=context,
                context_data=context_data,
                orientation=orientation,
                primary_agent=primary_agent,
                monitor=monitor,
            )
            for collaborator, orientation in selected_collaborators
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        collaborator_responses = {}
        for result in results:
            if isinstance(result, Exception):
                continue
            name, response = result
            if response:
                collaborator_responses[name] = response
        
        if collaborator_responses:
            formatted = "\n\n".join([f"[{name}]: {response}" for name, response in collaborator_responses.items()])
            return formatted
            
        return ""
    
    async def orchestrate(
        self,
        message: str,
        primary_agent: Agent,
        primary_response: str,
        context: str = "",
        monitor: Optional[Any] = None,
    ) -> str:
        """Post-response orchestration fallback."""
        if not hasattr(primary_agent, 'collaboration_enabled') or not primary_agent.collaboration_enabled:
            return primary_response
        
        agent_with_settings = await self.get_agent_with_collaborators(primary_agent.id)
        if not agent_with_settings or not agent_with_settings.collaborator_settings:
            return primary_response
        
        enabled = []
        neutral = []
        for setting in agent_with_settings.collaborator_settings:
            if setting.status == CollaborationStatus.ENABLED:
                enabled.append(setting.collaborator)
            elif setting.status == CollaborationStatus.NEUTRAL:
                neutral.append(setting.collaborator)
        
        if monitor:
            monitor.log_progress("Iniciando orquestração final pós-resposta")
            
        decision = await self.should_collaborate(message, primary_agent, enabled, neutral)
        if not decision["should_collaborate"] or not decision["agents_to_consult"]:
            return primary_response
            
        selected_collaborators = []
        for agent_info in decision["agents_to_consult"]:
            agent_id = agent_info.get("id")
            orientation = agent_info.get("orientation", "")
            for agent in (enabled + neutral):
                if str(agent.id) == str(agent_id):
                    selected_collaborators.append((agent, orientation))
                    break
        
        tasks = [
            self._invoke_collaborator(
                agent=collaborator,
                message=message,
                history=[],
                context=context,
                orientation=orientation,
                primary_agent=primary_agent,
                monitor=monitor,
            )
            for collaborator, orientation in selected_collaborators
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        collaborator_responses = {}
        for result in results:
            if isinstance(result, Exception):
                continue
            name, response = result
            if response:
                collaborator_responses[name] = response
        
        if not collaborator_responses:
            return primary_response
        
        from langchain_core.messages import SystemMessage
        collab_text = "\n\n".join([f"[{name}]: {response}" for name, response in collaborator_responses.items() if response])
        combine_prompt = f"""Você é o agente "{primary_agent.name}" finalizando uma resposta.

PERGUNTA ORIGINAL: "{message}"

SUA RESPOSTA INICIAL:
{primary_response}

CONTRIBUIÇÕES DOS ESPECIALISTAS:
{collab_text}

TAREFA:
Combine as informações em uma resposta única, coesa e natural.
- Não mencione que recebeu informações de outros agentes
- Mantenha sua personalidade e tom
- Integre as informações de forma fluida
- Se houver contradições, priorize sua resposta inicial
"""
        try:
            response = await self.llm.ainvoke([SystemMessage(content=combine_prompt)])
            return response.content
        except Exception as e:
            return primary_response
