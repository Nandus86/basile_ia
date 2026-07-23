"""
Output Result Schemas
"""
from pydantic import BaseModel, Field, model_validator
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime


class OutputSchema(BaseModel):
    messageRequired: bool = True
    sessionIdField: str = "session_id"
    mappings: Dict[str, str] = Field(default_factory=dict, description="Map internal field to external field")
    defaults: Dict[str, Any] = Field(default_factory=dict, description="Default values for missing fields")


class RetryConfig(BaseModel):
    maxRetries: int = 3
    delays: List[int] = Field(default=[1000, 5000, 15000])


class ResultInput(BaseModel):
    job_id: str
    output_url: Optional[str] = None
    pipeline_path: Optional[str] = None
    workflow_id: Optional[str] = None
    output_method: str = "POST"
    response: Dict[str, Any] = Field(default_factory=dict, description="Worker response data")
    agent_used: Optional[str] = None
    session_id: Optional[str] = None
    input_data: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    output_headers: Optional[Dict[str, Any]] = None
    retry_config: Optional[Dict[str, Any]] = None

    @model_validator(mode='before')
    @classmethod
    def wrap_raw_worker_payload(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "response" not in data:
                known_fields = {
                    "job_id", "output_url", "pipeline_path", "output_method", 
                    "agent_used", "session_id", "input_data", "output_schema", 
                    "output_headers", "retry_config"
                }
                new_data = {k: v for k, v in data.items() if k in known_fields}
                response_data = {k: v for k, v in data.items() if k not in known_fields}
                
                if "job_id" in data:
                    response_data["job_id"] = data["job_id"]
                    
                new_data["response"] = response_data
                return new_data
        return data


class ResultOutput(BaseModel):
    success: bool
    job_id: str
    message: str
    attempts: int = 0
    status: str


class ResultStatusResponse(BaseModel):
    job_id: str
    status: str
    attempts: int
    last_error: Optional[str]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    input_payload: Optional[Dict[str, Any]] = None
    output_payload: Optional[Dict[str, Any]] = None
    
    model_config = {"from_attributes": True}


class ResultListResponse(BaseModel):
    results: List[ResultStatusResponse]
    total: int