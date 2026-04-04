"""
Webhook Config Pydantic Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime


class WebhookConfigBase(BaseModel):
    name: str = Field(..., description="Friendly name for the webhook")
    path: str = Field(..., description="Unique path identifier (e.g., 'agente-marketing')")
    require_token: bool = Field(default=False, description="Require bearer token authentication")
    target_agent_id: Optional[UUID] = Field(None, description="Specific agent to route to, or null for auto-orchestration")
    sync_mode: bool = Field(default=False, description="Whether to run synchronously instead of using queue")
    is_active: bool = True

class WebhookConfigCreate(WebhookConfigBase):
    access_token: Optional[str] = Field(None, description="Bearer token to require if require_token is True")


class WebhookConfigUpdate(BaseModel):
    name: Optional[str] = None
    path: Optional[str] = None
    require_token: Optional[bool] = None
    access_token: Optional[str] = None
    target_agent_id: Optional[UUID] = None
    sync_mode: Optional[bool] = None
    is_active: Optional[bool] = None


class WebhookConfigResponse(WebhookConfigBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    # Optionally return the token or just a boolean indicating it exists
    has_token: bool = Field(..., description="Whether a token is configured")

    model_config = {"from_attributes": True}


class WebhookConfigList(BaseModel):
    webhooks: List[WebhookConfigResponse]
    total: int
