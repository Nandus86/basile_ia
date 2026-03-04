"""
Agent Orchestrator - Coordinates collaboration between specialist agents
"""
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any
from uuid import UUID

from app.models.agent import Agent, AgentCollaborator, CollaborationStatus
from app.config import settings


class AgentOrchestrator:
    """
    Orchestrates collaboration between specialist agents.
    
    Flow:
    1. Primary agent is selected based on message context
    2. Orchestrator checks if collaboration is needed
    3. Consults enabled/neutral collaborators as needed
    4. Combines responses into final answer
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            api_key=settings.OPENAI_API_KEY
        )
    
    async def get_agent_with_collaborators(self, agent_id: UUID) -> Optional[Agent]:
        """Fetch an agent with all its collaboration settings"""
        result = await self.db.execute(
            select(Agent)
            .options(
                selectinload(Agent.mcps),
                selectinload(Agent.collaborator_settings).selectinload(AgentCollaborator.collaborator)
            )
            .where(Agent.id == agent_id)
        )
        return result.scalar_one_or_none()
    
    async def should_collaborate(
        self, 
        message: str, 
        primary_agent: Agent,
        enabled_collaborators: List[Agent],
        neutral_collaborators: List[Agent]
    ) -> Dict[str, Any]:
        """
        Ask LLM if collaboration is needed and which agents to consult.
        
        Returns:
            {
                "should_collaborate": bool,
                "agents_to_consult": List[UUID],
                "reasoning": str
            }
        """
        if not primary_agent.collaboration_enabled:
            return {
                "should_collaborate": False,
                "agents_to_consult": [],
                "reasoning": "Collaboration is disabled for this agent"
            }
        
        if not enabled_collaborators and not neutral_collaborators:
            return {
                "should_collaborate": False,
                "agents_to_consult": [],
                "reasoning": "No collaborators available"
            }
        
        # Build agent descriptions
        enabled_desc = "\n".join([
            f"- {a.name}: {a.description or 'Sem descrição'}"
            for a in enabled_collaborators
        ]) or "Nenhum"
        
        neutral_desc = "\n".join([
            f"- {a.name}: {a.description or 'Sem descrição'}"
            for a in neutral_collaborators
        ]) or "Nenhum"
        
        prompt = f"""Você é um orquestrador que decide se um agente de IA precisa consultar outros especialistas.

AGENTE PRIMÁRIO: {primary_agent.name}
DESCRIÇÃO: {primary_agent.description or 'Especialista'}

MENSAGEM DO USUÁRIO: "{message}"

AGENTES PRIORITÁRIOS (consultar se relevante):
{enabled_desc}

AGENTES DISPONÍVEIS (usar apenas se realmente necessário):
{neutral_desc}

REGRAS:
1. Se o agente primário pode responder sozinho, não consulte ninguém
2. Consulte agentes prioritários se a mensagem envolve suas especialidades
3. Consulte agentes disponíveis apenas se absolutamente necessário
4. Máximo de 2 consultas por mensagem

Responda APENAS em JSON válido:
{{"should_collaborate": true/false, "agents": ["Nome do Agente 1", "Nome do Agente 2"], "reasoning": "Explicação breve"}}
"""
        
        try:
            response = await self.llm.ainvoke([
                SystemMessage(content=prompt)
            ])
            
            import json
            result_text = response.content.strip()
            
            # Clean markdown if present
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            result_text = result_text.strip()
            
            result = json.loads(result_text)
            
            # Map agent names to UUIDs
            all_collaborators = enabled_collaborators + neutral_collaborators
            agents_to_consult = []
            for name in result.get("agents", []):
                for agent in all_collaborators:
                    if agent.name.lower() == name.lower():
                        agents_to_consult.append(agent.id)
                        break
            
            return {
                "should_collaborate": result.get("should_collaborate", False),
                "agents_to_consult": agents_to_consult[:2],  # Max 2
                "reasoning": result.get("reasoning", "")
            }
            
        except Exception as e:
            print(f"[Orchestrator] Error deciding collaboration: {e}")
            return {
                "should_collaborate": False,
                "agents_to_consult": [],
                "reasoning": f"Error: {str(e)}"
            }
    
    async def consult_agent(
        self,
        agent: Agent,
        message: str,
        context: str = "",
        primary_response: str = ""
    ) -> str:
        """
        Consult a collaborator agent for additional information.
        
        Args:
            agent: The collaborator agent to consult
            message: Original user message
            context: Any relevant context from materials
            primary_response: Response from primary agent (if sequential)
        """
        collaboration_prompt = f"""Você é o agente "{agent.name}".
{agent.system_prompt}

---

Você está sendo consultado por outro agente para ajudar a responder uma pergunta.

PERGUNTA DO USUÁRIO: "{message}"

{"CONTEXTO PRÉVIO: " + primary_response if primary_response else ""}

{"INFORMAÇÕES DISPONÍVEIS: " + context if context else ""}

Forneça uma resposta focada na sua especialidade. 
Seja conciso e objetivo - sua resposta será combinada com outras.
"""
        
        try:
            response = await self.llm.ainvoke([
                SystemMessage(content=collaboration_prompt),
                HumanMessage(content=message)
            ])
            return response.content
        except Exception as e:
            print(f"[Orchestrator] Error consulting {agent.name}: {e}")
            return ""
    
    async def combine_responses(
        self,
        primary_agent: Agent,
        primary_response: str,
        collaborator_responses: Dict[str, str],
        original_message: str
    ) -> str:
        """
        Combine responses from primary agent and collaborators into a cohesive answer.
        """
        if not collaborator_responses:
            return primary_response
        
        collab_text = "\n\n".join([
            f"[{name}]: {response}"
            for name, response in collaborator_responses.items()
            if response
        ])
        
        combine_prompt = f"""Você é o agente "{primary_agent.name}" finalizando uma resposta.

PERGUNTA ORIGINAL: "{original_message}"

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
            response = await self.llm.ainvoke([
                SystemMessage(content=combine_prompt)
            ])
            return response.content
        except Exception as e:
            print(f"[Orchestrator] Error combining responses: {e}")
            return primary_response
    
    async def orchestrate(
        self,
        message: str,
        primary_agent: Agent,
        primary_response: str,
        context: str = ""
    ) -> str:
        """
        Main orchestration method.
        
        Args:
            message: User's original message
            primary_agent: The primary agent handling the request
            primary_response: Initial response from primary agent
            context: Material context if available
            
        Returns:
            Final combined response
        """
        # Check if collaboration is enabled
        if not hasattr(primary_agent, 'collaboration_enabled') or not primary_agent.collaboration_enabled:
            return primary_response
        
        # Get collaborators by status
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
            # BLOCKED agents are completely ignored
        
        print(f"[Orchestrator] Agent '{primary_agent.name}' has {len(enabled)} enabled, {len(neutral)} neutral collaborators")
        
        # Ask LLM if we should collaborate
        decision = await self.should_collaborate(message, primary_agent, enabled, neutral)
        
        if not decision["should_collaborate"]:
            print(f"[Orchestrator] No collaboration needed: {decision['reasoning']}")
            return primary_response
        
        print(f"[Orchestrator] Consulting: {decision['agents_to_consult']}, reason: {decision['reasoning']}")
        
        # Consult selected collaborators
        collaborator_responses = {}
        for agent_id in decision["agents_to_consult"]:
            agent = await self.get_agent_with_collaborators(agent_id)
            if agent:
                response = await self.consult_agent(
                    agent=agent,
                    message=message,
                    context=context,
                    primary_response=primary_response
                )
                if response:
                    collaborator_responses[agent.name] = response
        
        # Combine all responses
        if collaborator_responses:
            final_response = await self.combine_responses(
                primary_agent=primary_agent,
                primary_response=primary_response,
                collaborator_responses=collaborator_responses,
                original_message=message
            )
            return final_response
        
        return primary_response
