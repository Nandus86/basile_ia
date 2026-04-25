"""
Output Result Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime


class OutputSchema(BaseModel):
    mappings: Dict[str, str] = Field(default_factory=dict, description="Map internal field to external field")
    defaults: Dict[str, Any] = Field(default_factory=dict, description="Default values for missing fields")


class RetryConfig(BaseModel):
    maxRetries: int = 3
    delays: List[int] = Field(default=[1000, 5000, 15000])


class ResultInput(BaseModel):
    job_id: str
    output_url: str
    output_method: str = "POST"
    response: Dict[str, Any] = Field(..., description="Worker response data")
    agent_used: Optional[str] = None
    session_id: Optional[str] = None
    input_data: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    output_headers: Optional[Dict[str, Any]] = None
    retry_config: Optional[Dict[str, Any]] = None


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
    created_at: datetime
    updated_at: datetime
    sent_at: Optional[datetime]
    
    model_config = {"from_attributes": True}


class ResultListResponse(BaseModel):
    results: List[ResultStatusResponse]
    total: int