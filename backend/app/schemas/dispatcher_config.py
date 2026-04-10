"""
Dispatcher Config Pydantic Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime


class ButtonItem(BaseModel):
    label: str
    value: str
    action: str = ""

class DispatcherConfigBase(BaseModel):
    name: str = Field(..., description="Friendly name for the config")
    path: str = Field(..., description="Unique path identifier (e.g., 'campanha-abril')")
    
    buttons_enabled: bool = Field(default=False)
    buttons: List[ButtonItem] = Field(default_factory=list)
    image_enabled: bool = Field(default=False)
    
    messages_per_batch: int = Field(default=1)
    agent_id: Optional[UUID] = Field(None, description="Specific agent to route to")
    
    start_time: str = Field(default="08:00")
    end_time: str = Field(default="22:00")
    
    start_delay_seconds: int = Field(default=0)
    min_variation_seconds: int = Field(default=5)
    max_variation_seconds: int = Field(default=15)
    
    triggers: List[str] = Field(default_factory=list)
    index_max: int = Field(default=5)
    
    progress_callback_url: Optional[str] = Field(None)
    target_endpoint: Optional[str] = Field(None, description="Dynamic endpoint to post the dispatch request")
    is_active: bool = True

class DispatcherConfigCreate(DispatcherConfigBase):
    api_key: Optional[str] = Field(None, description="Bearer token/system.apikey to require")


class DispatcherConfigUpdate(BaseModel):
    name: Optional[str] = None
    path: Optional[str] = None
    api_key: Optional[str] = None
    buttons_enabled: Optional[bool] = None
    buttons: Optional[List[ButtonItem]] = None
    image_enabled: Optional[bool] = None
    messages_per_batch: Optional[int] = None
    agent_id: Optional[UUID] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    start_delay_seconds: Optional[int] = None
    min_variation_seconds: Optional[int] = None
    max_variation_seconds: Optional[int] = None
    triggers: Optional[List[str]] = None
    index_max: Optional[int] = None
    progress_callback_url: Optional[str] = None
    target_endpoint: Optional[str] = None
    is_active: Optional[bool] = None


class DispatcherConfigResponse(DispatcherConfigBase):
    id: UUID
    has_api_key: bool = Field(..., description="Whether an api_key is configured")
    agent_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DispatcherConfigList(BaseModel):
    configs: List[DispatcherConfigResponse]
    total: int
