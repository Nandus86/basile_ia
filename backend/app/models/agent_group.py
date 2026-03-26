"""
Agent Group Model - Hierarchical folders for organizing agents (supports sub-folders)
"""
from sqlalchemy import Column, String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.database import Base


class AgentGroup(Base):
    """Agent folders/groups with hierarchical support (parent_id for sub-folders)"""
    __tablename__ = "agent_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("agent_groups.id", ondelete="CASCADE"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Self-referential relationships
    parent = relationship("AgentGroup", remote_side=[id], backref="children")
    agents = relationship("Agent", back_populates="group")

    def __repr__(self):
        return f"<AgentGroup {self.name}>"
