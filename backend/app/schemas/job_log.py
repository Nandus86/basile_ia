from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime
import uuid


class JobLogSchema(BaseModel):
    id: uuid.UUID
    job_id: Optional[str] = None
    webhook_path: str
    status: str
    request_data: Optional[Any] = None
    response_data: Optional[Any] = None
    error_message: Optional[str] = None
    callback_url: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None

    class Config:
        from_attributes = True
