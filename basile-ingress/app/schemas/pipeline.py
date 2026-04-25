"""
Webhook Pipeline Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime


class InputSchema(BaseModel):
    messageRequired: bool = True
    sessionIdField: str = "session_id"
    mappings: Dict[str, str] = Field(default_factory=dict, description="Map external field to internal field")
    defaults: Dict[str, Any] = Field(default_factory=dict, description="Default values for missing fields")


class WebhookPipelineBase(BaseModel):
    name: str
    path: str
    is_active: bool = True
    description: Optional[str] = None
    input_schema: InputSchema
    
    auth_type: str = Field(default="none")
    auth_token: Optional[str] = None
    
    output_url: str
    output_method: str = "POST"
    output_schema: Optional[Dict[str, Any]] = None
    output_headers: Optional[Dict[str, Any]] = None
    
    retry_config: Dict[str, Any] = Field(default={"maxRetries": 3, "delays": [5000, 15000, 60000]})


class WebhookPipelineCreate(WebhookPipelineBase):
    pass


class WebhookPipelineUpdate(BaseModel):
    name: Optional[str] = None
    path: Optional[str] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None
    input_schema: Optional[InputSchema] = None
    auth_type: Optional[str] = None
    auth_token: Optional[str] = None
    output_url: Optional[str] = None
    output_method: Optional[str] = None
    output_schema: Optional[Dict[str, Any]] = None
    output_headers: Optional[Dict[str, Any]] = None
    retry_config: Optional[Dict[str, Any]] = None


class WebhookPipelineResponse(WebhookPipelineBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    has_auth_token: bool = Field(..., description="Whether auth token is configured")
    
    model_config = {"from_attributes": True}


class WebhookPipelineList(BaseModel):
    pipelines: List[WebhookPipelineResponse]
    total: int


class WebhookReceivedResponse(BaseModel):
    success: bool
    job_id: str
    message: str


class TestWebhookRequest(BaseModel):
    payload: Dict[str, Any] = Field(..., description="Test payload to send")


class TestWebhookResponse(BaseModel):
    success: bool
    pipeline: str
    normalized: Dict[str, Any]
    message: str