"""
Workflow Model
"""
from sqlalchemy import Column, String, Boolean, DateTime, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid

from app.database import Base


class Workflow(Base):
    """Visual Orchestration Workflow model (similar to n8n)"""
    __tablename__ = "workflows"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    
    # Stores the Vue Flow JSON structure (nodes, edges, positions, configurations)
    definition = Column(JSON, default=dict, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Workflow {self.name}>"
