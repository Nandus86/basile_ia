"""
Output Result Model
"""
from sqlalchemy import Column, String, Boolean, Text, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime, timezone
import uuid

from app.database import Base


class OutputResult(Base):
    __tablename__ = "output_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(String(255), nullable=False, index=True)
    output_url = Column(Text, nullable=False)
    output_method = Column(String(10), default="POST")
    
    input_data = Column(JSONB, nullable=True)
    output_data = Column(JSONB, nullable=True)
    response_data = Column(JSONB, nullable=True)
    
    status = Column(String(50), default="pending")
    attempts = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    
    output_schema = Column(JSONB, nullable=True)
    output_headers = Column(JSONB, nullable=True)
    retry_config = Column(JSONB, default={"maxRetries": 3, "delays": [1000, 5000, 15000]})
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    sent_at = Column(DateTime(timezone=True), nullable=True)
    
    def __repr__(self):
        return f"<OutputResult {self.job_id}>"