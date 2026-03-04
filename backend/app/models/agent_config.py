"""
Agent Resilience Configuration Model
Includes: Retry, Fallback, Timeout, Checkpoints, Human-in-the-loop
"""
from sqlalchemy import Column, String, Boolean, DateTime, Text, JSON, Integer, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.database import Base


class AgentConfig(Base):
    """Agent resilience and behavior configuration"""
    __tablename__ = "agent_configs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    # Retry Configuration
    max_retries = Column(Integer, default=3, nullable=False)
    retry_delay_seconds = Column(Float, default=1.0, nullable=False)
    retry_exponential_backoff = Column(Boolean, default=True, nullable=False)
    
    # Timeout Configuration
    timeout_seconds = Column(Integer, default=120, nullable=False)
    
    # Fallback Configuration
    fallback_enabled = Column(Boolean, default=False, nullable=False)
    fallback_model = Column(String(100), default="gpt-4o-mini")
    fallback_temperature = Column(Float, default=0.7)
    
    # Checkpoint Configuration (for state persistence and recovery)
    checkpoint_enabled = Column(Boolean, default=False, nullable=False)
    checkpoint_storage = Column(String(50), default="memory")  # memory, redis, postgres
    checkpoint_ttl_seconds = Column(Integer, default=3600)  # 1 hour default
    
    # Human-in-the-loop Configuration
    human_approval_enabled = Column(Boolean, default=False, nullable=False)
    human_approval_timeout_seconds = Column(Integer, default=300)  # 5 min default
    # JSON list of node names that require human approval before execution
    interrupt_before_nodes = Column(JSON, default=list)  # e.g., ["tool_execution", "external_api"]
    # JSON list of node names that require human approval after execution
    interrupt_after_nodes = Column(JSON, default=list)
    # Actions requiring approval: tool_call, mcp_execution, external_request
    require_approval_for = Column(JSON, default=list)
    
    # Rate Limiting
    rate_limit_enabled = Column(Boolean, default=False, nullable=False)
    max_requests_per_minute = Column(Integer, default=60)
    
    # Logging/Debug
    verbose_logging = Column(Boolean, default=False)
    log_tool_calls = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationship
    agent = relationship("Agent", back_populates="resilience_config")
    
    def __repr__(self):
        return f"<AgentConfig agent_id={self.agent_id}>"
    
    def to_dict(self):
        """Convert to dictionary for easy access"""
        return {
            "max_retries": self.max_retries,
            "retry_delay_seconds": self.retry_delay_seconds,
            "retry_exponential_backoff": self.retry_exponential_backoff,
            "timeout_seconds": self.timeout_seconds,
            "fallback_enabled": self.fallback_enabled,
            "fallback_model": self.fallback_model,
            "fallback_temperature": self.fallback_temperature,
            "checkpoint_enabled": self.checkpoint_enabled,
            "checkpoint_storage": self.checkpoint_storage,
            "checkpoint_ttl_seconds": self.checkpoint_ttl_seconds,
            "human_approval_enabled": self.human_approval_enabled,
            "human_approval_timeout_seconds": self.human_approval_timeout_seconds,
            "interrupt_before_nodes": self.interrupt_before_nodes or [],
            "interrupt_after_nodes": self.interrupt_after_nodes or [],
            "require_approval_for": self.require_approval_for or [],
            "rate_limit_enabled": self.rate_limit_enabled,
            "max_requests_per_minute": self.max_requests_per_minute,
            "verbose_logging": self.verbose_logging,
            "log_tool_calls": self.log_tool_calls
        }


class PendingApproval(Base):
    """Tracks pending human approvals for agent actions"""
    __tablename__ = "pending_approvals"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(String(255), nullable=False, index=True)
    
    # What needs approval
    action_type = Column(String(50), nullable=False)  # tool_call, mcp_execution, response
    action_name = Column(String(255))  # Tool name or node name
    action_data = Column(JSON)  # Full action details
    
    # Context
    message = Column(Text)  # Original user message
    context = Column(JSON)  # Additional context
    
    # Status
    status = Column(String(20), default="pending")  # pending, approved, rejected, expired
    approved_by = Column(String(255))  # User ID or identifier
    approval_note = Column(Text)
    
    # Checkpoint data for resuming
    checkpoint_id = Column(String(255))
    graph_state = Column(JSON)  # Serialized graph state
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True))
    resolved_at = Column(DateTime(timezone=True))
    
    def __repr__(self):
        return f"<PendingApproval {self.id} status={self.status}>"
