"""
Skill Model - AI Agent Skills definitions following Anthropics SKILL.md format
"""
from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, Table
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.database import Base


# Association table for agents <-> skills (many-to-many)
agent_skill_access = Table(
    "agent_skill_access",
    Base.metadata,
    Column("agent_id", UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
    Column("skill_id", UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)
)


class Skill(Base):
    """
    Skill model representing an Anthropic-style SKILL.md for agents.
    It contains an intent (what the user wanted) and the final markdown content.
    """
    __tablename__ = "skills"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    intent = Column(Text, nullable=True)        # The user's original request/description
    content_md = Column(Text, nullable=False)   # The generated SKILL.md payload
    is_active = Column(Boolean, default=True)
    always_active = Column(Boolean, default=False)  # Skill sempre considerada pelo router
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Folder group
    group_id = Column(UUID(as_uuid=True), ForeignKey("skill_groups.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    agents = relationship(
        "Agent",
        secondary=agent_skill_access,
        back_populates="skills",
        lazy="selectin"
    )
    group = relationship("SkillGroup", back_populates="skills")
    
    def __repr__(self):
        return f"<Skill {self.name}>"

