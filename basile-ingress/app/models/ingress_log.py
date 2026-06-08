"""
Ingress Log Model for Webhook requests
"""
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime, timezone
import uuid

from app.database import Base


class IngressLog(Base):
    __tablename__ = "ingress_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_id = Column(UUID(as_uuid=True), ForeignKey("webhook_pipelines.id", ondelete="CASCADE"), nullable=True)
    pipeline_path = Column(String(255), nullable=False, index=True)
    
    status = Column(String(50), nullable=False, index=True)
    
    raw_payload = Column(JSONB, nullable=True)
    output_payload = Column(JSONB, nullable=True)
    
    destination_url = Column(Text, nullable=True)
    response_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    
    duration_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    def __repr__(self):
        return f"<IngressLog {self.pipeline_path} - {self.status}>"
