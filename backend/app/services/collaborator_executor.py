"""
Collaborator Executor Service — Isolated invocation of collaborator agents

Handles the invocation of collaborator agents that are NOT orchestrators
and do NOT have collaboration enabled (pure task executor agents).

Each collaborator gets its own ephemeral STM in Redis, isolated from the
orchestrator's conversation history. The ephemeral STM lifecycle:

- WITHOUT Thinker: No history is saved. Each invocation starts from zero.
- WITH Thinker (pending tasks): History is persisted between invocations.
- WITH Thinker (all tasks complete): History + agent_memory are destroyed.
"""
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent


class CollaboratorExecutor:
    """
    Wraps collaborator invocation with isolated ephemeral history management.

    Use this for agents with is_orchestrator=False and collaboration_enabled=False
    (pure task executor agents called by orchestrators).
    """

    def __init__(self, db: AsyncSession, monitor: Optional[Any] = None):
        self.db = db
        self.monitor = monitor

    async def invoke(
        self,
        collaborator: Agent,
        instruction: str,
        session_id: Optional[str],
        context_data: Optional[Dict[str, Any]],
        primary_agent: Optional[Agent] = None,
        response_style: str = "structured",
    ) -> Tuple[str, str]:
        """
        Invoke a collaborator agent with isolated ephemeral history.

        The collaborator does NOT see the orchestrator's conversation history.
        Instead, it uses its own ephemeral STM that only persists when there
        are pending Thinker tasks.

        Args:
            collaborator: The collaborator agent to invoke
            instruction: Clear instruction from the orchestrator
            session_id: Session identifier for ephemeral STM key
            context_data: Structured context data from the request
            primary_agent: The orchestrator agent (for hierarchy)
            response_style: "structured" or "natural"

        Returns:
            Tuple of (agent_name, response_text)
        """
        from app.orchestrator.agent_orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator(self.db, monitor=self.monitor)

        # _invoke_collaborator now handles ephemeral STM internally.
        # We pass history=[] because the method loads its own history from Redis.
        name, response = await orchestrator._invoke_collaborator(
            agent=collaborator,
            message=instruction,
            history=[],
            context="",
            context_data=context_data,
            orientation=instruction,
            primary_agent=primary_agent,
            monitor=self.monitor,
            response_style=response_style,
        )

        return (name, response)
