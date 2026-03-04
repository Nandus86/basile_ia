"""
Webhook Config Model - Configuration for customizable webhook routes
"""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.database import Base


class WebhookConfig(Base):
    """Configuration for dynamic custom webhook endpoints"""
    __tablename__ = "webhook_configs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False) # Friendly name, e.g., "Marketing Integration"
    path = Column(String(255), nullable=False, unique=True, index=True) # The URL path, e.g., "agente-orch"
    
    # Authentication
    require_token = Column(Boolean, default=False, nullable=False) # Whether to check for a token
    access_token = Column(String(500), nullable=True) # The bearer token string expected
    
    # Routing
    target_agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True) # Specific agent or null for dynamic/Orchestrator
    
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    target_agent = relationship("Agent", foreign_keys=[target_agent_id], lazy="selectin")

    def __repr__(self):
        return f"<WebhookConfig {self.path} (agent={self.target_agent_id})>"
