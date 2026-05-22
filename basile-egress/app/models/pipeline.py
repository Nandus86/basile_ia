"""
Egress Pipeline Model
"""
from sqlalchemy import Column, String, Boolean, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime, timezone
import uuid

from app.database import Base


class EgressPipeline(Base):
    __tablename__ = "egress_pipelines"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    path = Column(String(255), nullable=False, unique=True, index=True)
    is_active = Column(Boolean, default=True)
    description = Column(Text, nullable=True)
    
    output_url = Column(Text, nullable=False)
    output_method = Column(String(10), default="POST")
    output_schema = Column(JSONB, nullable=True)
    output_headers = Column(JSONB, nullable=True)
    
    retry_config = Column(JSONB, default={"maxRetries": 3, "delays": [5000, 15000, 60000]})
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    def __repr__(self):
        return f"<EgressPipeline {self.path}>"
