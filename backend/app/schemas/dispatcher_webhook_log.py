from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime
import uuid

class DispatcherWebhookLogSchema(BaseModel):
    id: uuid.UUID
    webhook_path: str
    status_code: Optional[int] = None
    status: str
    request_payload: Optional[Any] = None
    response_payload: Optional[Any] = None
    error_message: Optional[str] = None
    contact_count: int
    created_at: Optional[datetime] = None
    duration_ms: Optional[int] = None

    model_config = {"from_attributes": True}
