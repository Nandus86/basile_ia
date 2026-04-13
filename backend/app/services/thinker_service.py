"""
Thinker Service - Strategic planning with global visibility

The Thinker is a special type of agent that:
- Has visibility into ALL agents in the organization
- Can see all skills, tools, and MCPs available
- Creates a structured execution plan based on the task
- Returns the plan for the calling agent to follow
"""
import json
import logging
from typing import List, Dict, Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.agent import Agent, agent_thinker_links, AgentCollaborator
from app.orchestrator.agent_factory import AgentFactory

logger = logging.getLogger(__name__)


async def get_linked_thinkers(db: AsyncSession, agent_id: UUID) -> List[Agent]:
    """
    Get all thinkers linked to an agent that are active.
    """
    result = await db.execute(
        select(Agent)
        .join(agent_thinker_links, Agent.id == agent_thinker_links.c.thinker_id)
        .where(
            agent_thinker_links.c.agent_id == agent_id,
            agent_thinker_links.c.is_active == True,
            Agent.is_active == True,
            Agent.is_thinker == True
        )
    )
    return result.scalars().all()


async def detect_matching_thinkers(
    message: str,
    thinkers: List[Agent]
) -> List[Agent]:
    """
    Detect which thinkers should be called based on message keywords.
    
    Returns all thinkers whose trigger_keywords match the message.
    """
    message_lower = message.lower()
    matching_thinkers = []
    
    for thinker in thinkers:
        keywords = thinker.trigger_keywords or []
        
        for keyword in keywords:
            if keyword.lower() in message_lower:
                matching_thinkers.append(thinker)
                logger.info(f"[ThinkerService] 🔑 Thinker '{thinker.name}' matched keyword: '{keyword}'")
                break
    
    return matching_thinkers


async def get_all_agents_for_thinker(
    db: AsyncSession,
    organization_id: Optional[UUID] = None
) -> List[Dict[str, Any]]:
    """
    Get all agents with their capabilities for the thinker.
    This provides the global visibility that the thinker needs.
    """
    query = select(Agent).where(Agent.is_active == True)
    
    result = await db.execute(
        query.options(
            selectinload(Agent.skills),
            selectinload(Agent.mcps),
            selectinload(Agent.collaborator_settings)
                .selectinload(AgentCollaborator.collaborator)
        )
    )
    
    all_agents = result.scalars().all()
    
    agents_data = []
    for agent in all_agents:
        # Get collaborator info
        collaborators = []
        for collab_setting in agent.collaborator_settings:
            collab = collab_setting.collaborator
            collaborators.append({
                "name": collab.name,
                "description": collab.description or "",
                "status": collab_setting.status.value
            })
        
        # Get skills
        skills = []
        for skill in agent.skills:
            if skill.is_active:
                skills.append({
                    "name": skill.name,
                    "intent": skill.intent or ""
                })
        
        # Get MCPs/tools
        tools = [{"name": mcp.name, "description": mcp.description or ""} for mcp in agent.mcps]
        
        agents_data.append({
            "id": str(agent.id),
            "name": agent.name,
            "description": agent.description or "",
            "is_orchestrator": agent.is_orchestrator,
            "is_thinker": agent.is_thinker,
            "model": agent.model,
            "skills": skills,
            "tools": tools,
            "collaborators": collaborators,
            "trigger_keywords": agent.trigger_keywords or []
        })
    
    return agents_data


async def call_thinker(
    db: AsyncSession,
    thinker: Agent,
    message: str,
    context_data: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Call a thinker agent to generate a strategic plan.
    
    Returns a structured plan with:
    - visao_geral: Strategic overview
    - passos: List of steps with agent assignments
    - contexto_necessario: Context needed for execution
    """
    from langchain_core.messages import SystemMessage, HumanMessage
    
    factory = AgentFactory(db)
    agent_config = await factory.get_agent_config(thinker, context_data=context_data)
    
    # Get all agents for global visibility
    all_agents = await get_all_agents_for_thinker(db)
    agents_json = json.dumps(all_agents, ensure_ascii=False, indent=2)
    
    # Build strategic prompt for thinker
    thinker_instruction = thinker.thinker_prompt or (
        "\n\nVocê é um Thinker (Pensador Estratégico) com VISÃO GLOBAL de todo o sistema.\n"
        "Sua tarefa é analisar a tarefa solicitada e criar um PLANO DE EXECUÇÃO detalhado.\n\n"
    )
    
    thinker_instruction += f"""
## Sua Visão Global - Agentes Disponíveis

{agents_json}

## Sua Tarefa

Analise a mensagem do usuário abaixo e crie um plano de execução:

MENSAGEM DO USUÁRIO: {message}

## Output Obrigatório

Retorne EXATAMENTE este JSON (não inclua nenhuma outra coisa):

{{
  "visao_geral": "Breve descrição do que será feito",
  "passos": [
    {{
      "ordem": 1,
      "agente": "Nome do agente que deve executar",
      "acao": "O que este agente deve fazer",
      "dados_necessarios": {{"campo": "valor"}}
    }}
  ],
  "aviso": "Qualquer observação importante"
}}

IMPORTANTE:
- Seja específico nos passos
- Use APENAS os nomes dos agentes listados acima
- Considere dependências entre passos
"""
    
    # Override with thinker-specific model if configured
    original_model = agent_config.get("model")
    if thinker.thinker_model:
        agent_config["model"] = thinker.thinker_model
        agent_config["config"] = agent_config.get("config", {})
        agent_config["config"]["is_reasoning_model"] = False
    
    # Build messages
    messages = [HumanMessage(content=message)]
    
    try:
        response = await factory.invoke_agent(
            agent_config=agent_config,
            messages=messages,
            rag_context=None,
            context_data=context_data
        )
        
        # Try to parse the JSON response
        try:
            # Find JSON in response
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = response[start:end]
                plan = json.loads(json_str)
                return plan
        except json.JSONDecodeError:
            logger.warning(f"[ThinkerService] ⚠️ Failed to parse thinker JSON, returning raw response")
        
        # Fallback: return structured with raw response
        return {
            "visao_geral": response[:500],
            "passos": [],
            "aviso": "Plano não estruturado retornado"
        }
        
    except Exception as e:
        logger.error(f"[ThinkerService] ❌ Error calling thinker '{thinker.name}': {e}")
        return {
            "visao_geral": f"Erro ao processar: {str(e)}",
            "passos": [],
            "aviso": "Fallback devido a erro"
        }


async def execute_thinker_planning(
    db: AsyncSession,
    agent: Agent,
    message: str,
    context_data: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict[str, Any]]] = None
) -> Optional[Dict[str, Any]]:
    """
    Main entry point: Check if any thinkers should be called based on message,
    call them, and return the aggregated plans.
    
    Returns None if no thinkers matching, or aggregated plan if thinkers called.
    """
    # Get linked thinkers
    linked_thinkers = await get_linked_thinkers(db, agent.id)
    
    if not linked_thinkers:
        logger.debug(f"[ThinkerService] No thinkers linked to agent '{agent.name}'")
        return None
    
    # Detect matching thinkers by keywords
    matching_thinkers = await detect_matching_thinkers(message, linked_thinkers)
    
    if not matching_thinkers:
        logger.debug(f"[ThinkerService] No thinkers matched keywords in message")
        return None
    
    # Call all matching thinkers and aggregate their plans
    all_plans = {
        "visao_geral": "",
        "passos": [],
        "avisos": []
    }
    
    for thinker in matching_thinkers:
        logger.info(f"[ThinkerService] 🤔 Calling thinker '{thinker.name}' for planning")
        plan = await call_thinker(
            db=db,
            thinker=thinker,
            message=message,
            context_data=context_data,
            history=history
        )
        
        if plan.get("visao_geral"):
            all_plans["visao_geral"] += f"\n{plan.get('visao_geral', '')}"
        
        if plan.get("passos"):
            all_plans["passos"].extend(plan.get("passos", []))
        
        if plan.get("aviso"):
            all_plans["avisos"].append(plan.get("aviso"))
    
    # Build final aggregated response
    final_plan = {
        "visao_geral": all_plans["visao_geral"].strip(),
        "passos": all_plans["passos"],
        "avisos": all_plans["avisos"],
        "thinkers_chamados": [t.name for t in matching_thinkers]
    }
    
    logger.info(f"[ThinkerService] ✅ Generated plan with {len(all_plans['passos'])} steps from {len(matching_thinkers)} thinker(s)")
    
    return final_plan