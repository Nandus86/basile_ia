from sqlalchemy import Column, String, Integer, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid

from app.database import Base

class DispatcherWebhookLog(Base):
    """Logs of incoming webhooks hitting the dispatcher before entering rabbitmq/worker."""
    __tablename__ = "dispatcher_webhook_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    webhook_path = Column(String(255), nullable=False, index=True)
    status_code = Column(Integer, nullable=True) # e.g. 202, 422, 403, 500
    status = Column(String(50), default="pending", nullable=False) # pending, success, failed, validation_error, unauthorized
    request_payload = Column(JSON, nullable=True)
    response_payload = Column(JSON, nullable=True)
    error_message = Column(String, nullable=True)
    contact_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    duration_ms = Column(Integer, nullable=True)

    def __repr__(self):
        return f"<DispatcherWebhookLog {self.id} | path={self.webhook_path} | status={self.status}>"
