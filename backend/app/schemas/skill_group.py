from pydantic import BaseModel, Field, UUID4
from typing import Optional, List
from datetime import datetime


class SkillGroupBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    is_active: bool = True


class SkillGroupCreate(SkillGroupBase):
    pass


class SkillGroupUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class SkillGroupResponse(SkillGroupBase):
    id: UUID4
    created_at: datetime
    updated_at: datetime
    skill_count: int = 0

    class Config:
        from_attributes = True
