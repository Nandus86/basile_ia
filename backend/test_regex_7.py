import asyncio
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any

class ProcessRequest(BaseModel):
    message: str
    session_id: str
    agent_id: Optional[str] = None
    user_access_level: str = "normal"
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    context_data: Optional[Dict[str, Any]] = None
    transition_data: Optional[Dict[str, Any]] = None
    callback_url: Optional[str] = None

    model_config = ConfigDict(extra="allow")

payload_json = {
  "message": "quais eventos tem na igreja?",
  "session_id": "68ff5a3c4177621d0b00faa85543999284670",
  "church": {
    "_id": "68ff5a3c4177621d0b00faa9",
    "role": "church",
    "phone": "5547992034898"
  },
  "global": {
    "phone": "5543999284670"
  }
}

req = ProcessRequest(**payload_json)
print("Request model extra:", req.model_extra)
full_payload = {**req.model_dump(), **(req.model_extra or {})}
print("Full payload:", full_payload)
print("Is church a dict?", isinstance(full_payload["church"], dict))
