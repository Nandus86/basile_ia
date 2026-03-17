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


def get_skill_capability_description(skill_obj) -> str:
    """
    Extracts a concise capability description from a Skill's content_md and intent.
    Used for Capability Maps in orchestrator routing.
    """
    import re
    
    intent = getattr(skill_obj, "intent", "") or ""
    content_md = getattr(skill_obj, "content_md", "") or ""
    
    if not content_md:
        return intent.replace("\n", " ").strip()
    
    # Try to find tool names (common pattern: - **tool_name**)
    tools = re.findall(r'-\s+\*\*(.*?)\*\*', content_md)
    tools_text = f" [Usa: {', '.join(tools)}]" if tools else ""
    
    # Take the first meaningful paragraph as the description, skipping headers
    description = ""
    lines = content_md.split("\n")
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        description = line
        break
        
    if not description:
        description = intent or "Sem descrição detalhada"
        
    # Clean up: no newlines, limited length
    description = description.replace("\n", " ").strip()
    if len(description) > 300:
        description = description[:297] + "..."
        
    return f"{description}{tools_text}".strip()
