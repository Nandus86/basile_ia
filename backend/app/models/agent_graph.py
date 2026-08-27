"""
Agent Graph Model - Visual Multi-Agent Orchestration Graphs
"""
from sqlalchemy import Column, String, Boolean, DateTime, Text, JSON, Integer, ForeignKey, Table
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.database import Base


# Association table for agents <-> agent_graphs as tools (many-to-many)
agent_graph_tool_access = Table(
    "agent_graph_tool_access",
    Base.metadata,
    Column("agent_id", UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
    Column("graph_id", UUID(as_uuid=True), ForeignKey("agent_graphs.id", ondelete="CASCADE"), primary_key=True),
    Column("tool_name", String(100), nullable=True),
    Column("tool_description", Text, nullable=True)
)


class AgentGraph(Base):
    """
    Agent Graph definition for multi-agent workflows, reasoning loops,
    and parallel team execution.
    """
    __tablename__ = "agent_graphs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # Stores the Vue Flow JSON structure (nodes, edges, positions, configurations)
    definition = Column(JSON, default=dict, nullable=False)

    # Execution limits for loop and timeout control
    recursion_limit = Column(Integer, default=25, nullable=False)
    timeout_seconds = Column(Integer, default=60, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Agents that use this graph as their primary execution graph
    assigned_agents = relationship(
        "Agent",
        foreign_keys="Agent.graph_id",
        back_populates="graph"
    )

    # Agents that have this graph attached as a callable tool
    tool_users = relationship(
        "Agent",
        secondary=agent_graph_tool_access,
        back_populates="graph_tools"
    )

    def __repr__(self):
        return f"<AgentGraph {self.name} (id={self.id})>"
