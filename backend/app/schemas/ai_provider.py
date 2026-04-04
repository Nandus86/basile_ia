"""
AI Provider Pydantic Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime


class AIProviderBase(BaseModel):
    name: str = Field(..., description="Provider Name (e.g., openai, anthropic, openrouter)")
    base_url: Optional[str] = Field(None, description="Custom base URL for the API")
    default_model: Optional[str] = Field(None, description="Default model to use")
    is_active: bool = True


class AIProviderCreate(AIProviderBase):
    api_key: str = Field(..., description="API Key or Token")

class AIProviderUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    default_model: Optional[str] = None
    is_active: Optional[bool] = None

class AIProviderResponse(AIProviderBase):
    id: UUID
    # Never return the full api_key in responses for security
    api_key_configured: bool = Field(..., description="Whether an API key is configured")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AIProviderList(BaseModel):
    providers: List[AIProviderResponse]
    total: int
