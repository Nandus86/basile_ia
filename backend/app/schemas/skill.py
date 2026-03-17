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
    
    # Tools are now identified by ## tool_name headers
    # Descriptions are within << >> markers
    tool_sections = re.findall(r'##\s*(.*?)\n', content_md)
    descriptions = re.findall(r'<<\s*(.*?)\s*>>', content_md)
    
    tools_parts = []
    # If we have headers, those are our technical tool/method names
    for section in tool_sections:
        tools_parts.append(section.strip())
        
    tools_text = f" [Usa: {', '.join(tools_parts)}]" if tools_parts else ""
    
    # Use the first << >> as the primary description if available, 
    # otherwise fall back to the first paragraph
    description = ""
    if descriptions:
        description = descriptions[0].strip()
    else:
        # Fallback to first non-header paragraph
        lines = content_md.split("\n")
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
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
