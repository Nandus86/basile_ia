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
    session_id: Optional[str] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm(cls, obj):
        data = {}
        for field in ["id", "job_id", "webhook_path", "status", "request_data", "response_data", 
                      "error_message", "callback_url", "created_at", "completed_at", "duration_ms"]:
            value = getattr(obj, field, None)
            data[field] = value
        
        request_data = obj.request_data
        if isinstance(request_data, dict):
            data["session_id"] = request_data.get("session_id")
        elif isinstance(request_data, str) and request_data:
            try:
                import json
                parsed = json.loads(request_data)
                data["session_id"] = parsed.get("session_id") if isinstance(parsed, dict) else None
            except:
                data["session_id"] = None
        
        return cls(**data)
