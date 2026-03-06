"""
Skill Schemas
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class SkillBase(BaseModel):
    """Base schema for a skill"""
    name: str = Field(..., min_length=1, max_length=255)
    intent: Optional[str] = None
    content_md: str
    is_active: bool = True


class SkillCreate(SkillBase):
    """Schema for creating a new skill"""
    pass


class SkillUpdate(BaseModel):
    """Schema for updating an existing skill"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    intent: Optional[str] = None
    content_md: Optional[str] = None
    is_active: Optional[bool] = None


class SkillResponse(BaseModel):
    """Schema for returning a skill"""
    id: UUID
    name: str
    intent: Optional[str] = None
    content_md: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SkillSummary(BaseModel):
    """Summary of a skill (e.g., for list views or embedding in agent response)"""
    id: UUID
    name: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class SkillList(BaseModel):
    """Schema for a list of skills"""
    skills: List[SkillResponse]
    total: int

    model_config = ConfigDict(from_attributes=True)

class SkillGenerateRequest(BaseModel):
    """Schema for requesting a skill generation via LLM"""
    name: str = Field(..., description="Nome da skill")
    intent: str = Field(..., description="O que a skill deve fazer")

class SkillGenerateResponse(BaseModel):
    """Schema for the LLM skill generation response"""
    content_md: str
