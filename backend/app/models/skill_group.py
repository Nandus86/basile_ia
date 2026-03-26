"""
Skill Group Model - Simple folders for organizing skills
"""
from sqlalchemy import Column, String, DateTime, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.database import Base


class SkillGroup(Base):
    """Skill folders/groups for organizing skills"""
    __tablename__ = "skill_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    skills = relationship("Skill", back_populates="group")

    def __repr__(self):
        return f"<SkillGroup {self.name}>"
