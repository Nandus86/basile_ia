"""
Emotional Profile Schemas
"""
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class EmotionalProfileBase(BaseModel):
    """Base emotional profile schema"""
    code: str
    name: str
    description: Optional[str] = None
    category: str = "neutral"
    icon: str = "mdi-emoticon"
    color: str = "grey"
    prompt_template: str = ""


class EmotionalProfileCreate(EmotionalProfileBase):
    """Schema for creating an emotional profile"""
    is_active: bool = True


class EmotionalProfileUpdate(BaseModel):
    """Schema for updating an emotional profile"""
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    prompt_template: Optional[str] = None
    is_active: Optional[bool] = None


class EmotionalProfileResponse(BaseModel):
    """Schema for emotional profile response"""
    id: UUID
    code: str
    name: str
    description: Optional[str] = None
    category: str
    icon: str
    color: str
    prompt_template: str = ""
    is_system: bool = False
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmotionalProfileSummary(BaseModel):
    """Summary schema for embedding in agent responses"""
    id: UUID
    code: str
    name: str
    category: str
    icon: str
    color: str

    model_config = ConfigDict(from_attributes=True)


class EmotionalProfileList(BaseModel):
    """Schema for list of emotional profiles"""
    profiles: List[EmotionalProfileResponse]
    total: int
