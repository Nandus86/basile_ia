from pydantic import BaseModel, model_validator
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
    session_id: Optional[str] = None

    model_config = {"from_attributes": True}

    @model_validator(mode='after')
    def extract_session_id(self):
        request_data = self.request_data
        if isinstance(request_data, dict):
            self.session_id = request_data.get("session_id")
        elif isinstance(request_data, str) and request_data:
            try:
                import json
                parsed = json.loads(request_data)
                if isinstance(parsed, dict):
                    self.session_id = parsed.get("session_id")
            except:
                pass
        return self
