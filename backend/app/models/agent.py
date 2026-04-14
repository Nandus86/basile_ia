"""
Agent Model - AI agents with hierarchical access and collaboration
"""
from sqlalchemy import Column, String, Boolean, DateTime, Text, JSON, Enum, ForeignKey, Table
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid
import enum

from app.database import Base


# Association table for agents <-> mcps (many-to-many)
agent_mcp_access = Table(
    "agent_mcp_access",
    Base.metadata,
    Column("agent_id", UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
    Column("mcp_id", UUID(as_uuid=True), ForeignKey("mcps.id", ondelete="CASCADE"), primary_key=True)
)

# Association table for agents <-> mcp_groups (many-to-many)
agent_mcp_group_access = Table(
    "agent_mcp_group_access",
    Base.metadata,
    Column("agent_id", UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
    Column("mcp_group_id", UUID(as_uuid=True), ForeignKey("mcp_groups.id", ondelete="CASCADE"), primary_key=True)
)

# Association table for agents <-> thinkers (many-to-many)
# A thinker can be linked to multiple agents, and an agent can have multiple thinkers
agent_thinker_links = Table(
    "agent_thinker_links",
    Base.metadata,
    Column("agent_id", UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
    Column("thinker_id", UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
    Column("is_active", Boolean, default=True, nullable=False)
)


class AccessLevel(str, enum.Enum):
    """Vertical access levels for agents - hierarchical permission system"""
    MINIMUM = "minimum"    # 🔵 Basic access - only basic support
    NORMAL = "normal"      # 🟢 Standard access - registered users
    PRO = "pro"            # 🟡 Pro access - advanced features
    PREMIUM = "premium"    # 🔴 Premium access - full access to all features

    @classmethod
    def get_level_value(cls, level: 'AccessLevel') -> int:
        """Get numeric value for level comparison"""
        order = {cls.MINIMUM: 0, cls.NORMAL: 1, cls.PRO: 2, cls.PREMIUM: 3}
        return order.get(level, 0)
    
    def can_access(self, agent_level: 'AccessLevel') -> bool:
        """Check if this level can access an agent of given level"""
        return AccessLevel.get_level_value(self) >= AccessLevel.get_level_value(agent_level)


class CollaborationStatus(str, enum.Enum):
    """Status for agent collaboration permissions - horizontal collaboration"""
    ENABLED = "enabled"    # ✅ Priority - orchestrator should consider using
    NEUTRAL = "neutral"    # ⚪ Available - orchestrator can use if needed
    BLOCKED = "blocked"    # 🚫 Forbidden - never accessible


class AgentCollaborator(Base):
    """Defines collaboration permissions between agents"""
    __tablename__ = "agent_collaborators"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    collaborator_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(Enum(CollaborationStatus), default=CollaborationStatus.NEUTRAL, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    agent = relationship("Agent", foreign_keys=[agent_id], back_populates="collaborator_settings")
    collaborator = relationship("Agent", foreign_keys=[collaborator_id])
    
    def __repr__(self):
        return f"<AgentCollaborator(agent={self.agent_id}, collaborator={self.collaborator_id}, status={self.status})>"


class Agent(Base):
    """AI Agent model with hierarchical access and collaboration support"""
    __tablename__ = "agents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    system_prompt = Column(Text, nullable=False)
    model = Column(String(100), default="gpt-4o-mini")
    temperature = Column(String(10), default="0.7")
    max_tokens = Column(String(10), default="2000")
    config = Column(JSON, default=dict)
    is_active = Column(Boolean, default=True)
    
    # Hierarchical access level (vertical)
    access_level = Column(
        Enum(AccessLevel, values_callable=lambda x: [e.value for e in x], name='accesslevel', create_type=False),
        default=AccessLevel.NORMAL,
        nullable=False
    )
    
    # Collaboration settings (horizontal)
    collaboration_enabled = Column(Boolean, default=True, nullable=False)
    
    # Orchestrator mode - hierarchical control over subordinates
    is_orchestrator = Column(Boolean, default=False, nullable=False)
    orchestrator_config = Column(JSON, default=dict)  # Additional orchestrator settings
    
    # Response style for collaborator output ("structured" or "natural")
    response_style = Column(String(20), default="structured", nullable=False)

    # Planner mode
    is_planner = Column(Boolean, default=False, nullable=False)
    planner_prompt = Column(Text, nullable=True)
    planner_model = Column(String(100), nullable=True)
    
    # Guardrail Validator mode
    is_guardrail_active = Column(Boolean, default=False, nullable=False)
    guardrail_prompt = Column(Text, nullable=True)
    guardrail_model = Column(String(100), nullable=True)
    
    # Thinker mode - strategic planning with global visibility
    is_thinker = Column(Boolean, default=False, nullable=False)
    thinker_prompt = Column(Text, nullable=True)  # Custom strategic prompt
    thinker_model = Column(String(100), nullable=True)  # Override model for thinker
    thinker_restrictive = Column(Boolean, default=False, nullable=False)  # Force to follow plan strictly
    thinker_always_active = Column(Boolean, default=False, nullable=False)  # Always active without keyword
    thinker_keywords = Column(JSON, nullable=True)  # Custom keywords to activate thinker
    thinker_memory_enabled = Column(Boolean, default=True, nullable=False)  # Enable Redis memory for task list
    
    # New status configuration for long-running jobs
    status_updates_enabled = Column(Boolean, default=False)
    status_updates_config = Column(JSON, nullable=True) # {delay_1_seconds: X, delay_1_message: Y, ...}
    
    # Intelligent Vector Memory - for storing temporal/qualitative data about contacts
    vector_memory_enabled = Column(Boolean, default=False, nullable=False)
    
    # RLHF Training Memory - for storing behavioral rules based on chat feedback (thumbs up/down)
    training_memory_enabled = Column(Boolean, default=False, nullable=False)
    
    # Structured Output - custom JSON schema per agent (LLM Context)
    output_schema = Column(JSON, nullable=True, default=None)
    # Example: {"output": {"type": "string"}, "tag": {"type": "string", "enum": [...]}}
    
    # Structured Input - custom JSON schema defining expected context_data fields (LLM Context)
    input_schema = Column(JSON, nullable=True, default=None)
    # Example: {"nome_usuario": {"type": "string", "description": "Nome do usuário"}, ...}

    # System Transition Output - data meant to be appended to the final response, bypassing LLM
    transition_output_schema = Column(JSON, nullable=True, default=None)
    # Example: {"session_id": {"type": "string"}, "target_queue": {"type": "string"}}

    # System Transition Input - data meant to be received and kept in state, bypassing LLM
    transition_input_schema = Column(JSON, nullable=True, default=None)
    # Example: {"session_id": {"type": "string", "required": True}}
    
    # Priority keywords that force the orchestrator to call this agent
    trigger_keywords = Column(JSON, default=list)
    
    # Dynamic entity memory path - e.g. $request.church._id
    entity_memory_path = Column(String(255), nullable=True)
    
    # Emotional profile - pre-defined communication style
    emotional_profile_id = Column(UUID(as_uuid=True), ForeignKey("emotional_profiles.id", ondelete="SET NULL"), nullable=True)
    emotional_intensity = Column(String(20), default="medium")  # low, medium, high

    # AI Provider configuration
    provider_id = Column(UUID(as_uuid=True), ForeignKey("ai_providers.id", ondelete="SET NULL"), nullable=True)

    # Folder group (hierarchical)
    group_id = Column(UUID(as_uuid=True), ForeignKey("agent_groups.id", ondelete="SET NULL"), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # MCPs the agent can use
    mcps = relationship(
        "MCP",
        secondary=agent_mcp_access,
        lazy="selectin"
    )
    
    # MCP Groups the agent can use
    mcp_groups = relationship(
        "MCPGroup",
        secondary=agent_mcp_group_access,
        lazy="selectin"
    )
    
    # Documents the agent can access for RAG
    documents = relationship(
        "Document",
        secondary="agent_document_access",
        back_populates="agents",
        lazy="selectin"
    )
    
    # Resilience configuration (one-to-one)
    resilience_config = relationship(
        "AgentConfig",
        back_populates="agent",
        uselist=False,
        lazy="selectin",
        cascade="all, delete-orphan"
    )
    
    # Skills the agent can use
    skills = relationship(
        "Skill",
        secondary="agent_skill_access",
        back_populates="agents",
        lazy="selectin"
    )

    # Information Bases the agent can use for RAG
    information_bases = relationship(
        "InformationBase",
        secondary="agent_info_base_access",
        back_populates="agents",
        lazy="selectin"
    )

    # VFS Knowledge Bases for RAG 3.0
    vfs_knowledge_bases = relationship(
        "VFSKnowledgeBase",
        secondary="agent_vfs_knowledge_base_access",
        back_populates="agents",
        lazy="selectin"
    )
    
    # Collaboration settings (agents this agent can collaborate with)
    collaborator_settings = relationship(
        "AgentCollaborator",
        foreign_keys="AgentCollaborator.agent_id",
        back_populates="agent",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    # Folder group relationship
    group = relationship("AgentGroup", back_populates="agents")
    
    # Emotional profile relationship
    emotional_profile = relationship(
        "EmotionalProfile",
        lazy="selectin"
    )
    
    # AI Provider relationship
    provider = relationship(
        "AIProvider",
        lazy="selectin"
    )
    
    def __repr__(self):
        return f"<Agent {self.name} (level={self.access_level.value})>"
    
    def get_enabled_collaborators(self):
        """Get collaborators with ENABLED status"""
        return [c.collaborator for c in self.collaborator_settings if c.status == CollaborationStatus.ENABLED]
    
    def get_neutral_collaborators(self):
        """Get collaborators with NEUTRAL status"""
        return [c.collaborator for c in self.collaborator_settings if c.status == CollaborationStatus.NEUTRAL]
    
    def get_available_collaborators(self):
        """Get all non-blocked collaborators (enabled + neutral)"""
        return [c.collaborator for c in self.collaborator_settings if c.status != CollaborationStatus.BLOCKED]
    
    def get_linked_thinkers(self, db):
        """Get thinkers linked to this agent via agent_thinker_links"""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        
        result = db.execute(
            select(Agent)
            .join(agent_thinker_links, Agent.id == agent_thinker_links.c.thinker_id)
            .where(
                agent_thinker_links.c.agent_id == self.id,
                agent_thinker_links.c.is_active == True,
                Agent.is_active == True,
                Agent.is_thinker == True
            )
        )
        return result.scalars().all()
