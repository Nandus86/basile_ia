from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID
from enum import Enum

from app.schemas.emotional_profile import EmotionalProfileSummary
from app.schemas.skill import SkillSummary


class AccessLevelEnum(str, Enum):
    """Vertical access levels"""
    MINIMUM = "minimum"
    NORMAL = "normal"
    PRO = "pro"
    PREMIUM = "premium"


class CollaborationStatusEnum(str, Enum):
    """Horizontal collaboration status"""
    ENABLED = "enabled"
    NEUTRAL = "neutral"
    BLOCKED = "blocked"


class MCPSummary(BaseModel):
    """Summary of an MCP linked to agent"""
    id: UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


class MCPGroupSummary(BaseModel):
    """Summary of an MCP Group linked to agent"""
    id: UUID
    name: str
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CollaboratorSummary(BaseModel):
    """Summary of a collaborator agent"""
    id: UUID
    name: str
    status: CollaborationStatusEnum

    model_config = ConfigDict(from_attributes=True)


class CollaboratorUpdate(BaseModel):
    """Update collaboration status for an agent"""
    collaborator_id: UUID
    status: CollaborationStatusEnum


class CollaboratorsUpdateRequest(BaseModel):
    """Request to update all collaborators for an agent"""
    collaborators: List[CollaboratorUpdate]


class AgentBase(BaseModel):
    """Base agent schema"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    system_prompt: str = Field(..., min_length=1)
    model: str = Field(default="gpt-4o-mini")
    temperature: str = Field(default="0.7")
    max_tokens: str = Field(default="2000")
    config: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    vector_memory_enabled: bool = False
    training_memory_enabled: bool = False
    status_updates_enabled: bool = False
    status_updates_config: Optional[Dict[str, Any]] = Field(default=None)
    planner_prompt: Optional[str] = None
    planner_model: Optional[str] = None
    is_guardrail_active: bool = False
    guardrail_prompt: Optional[str] = None
    guardrail_model: Optional[str] = None
    trigger_keywords: List[str] = Field(default_factory=list)
    entity_memory_path: Optional[str] = None


class AgentCreate(AgentBase):
    """Schema for creating an agent"""
    access_level: AccessLevelEnum = AccessLevelEnum.NORMAL
    collaboration_enabled: bool = True
    mcp_ids: Optional[List[UUID]] = Field(default=[], description="IDs dos MCPs com acesso")
    mcp_group_ids: Optional[List[UUID]] = Field(default=[], description="IDs dos Grupos MCP com acesso")
    skill_ids: Optional[List[UUID]] = Field(default=[], description="IDs das Skills com acesso")
    is_orchestrator: bool = False
    is_planner: bool = False
    emotional_profile_id: Optional[UUID] = None
    emotional_intensity: str = "medium"
    output_schema: Optional[Dict[str, Any]] = Field(default=None, description="Schema JSON personalizado para saída estruturada")
    input_schema: Optional[Dict[str, Any]] = Field(default=None, description="Schema JSON que define os campos de context_data esperados na entrada")
    transition_output_schema: Optional[Dict[str, Any]] = Field(default=None, description="Schema JSON de metadados a serem anexados inalterados na resposta")
    transition_input_schema: Optional[Dict[str, Any]] = Field(default=None, description="Schema JSON de metadados de sessão recebidos na entrada e preservados")


class AgentUpdate(BaseModel):
    """Schema for updating an agent"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[str] = None
    max_tokens: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    access_level: Optional[AccessLevelEnum] = None
    collaboration_enabled: Optional[bool] = None
    mcp_ids: Optional[List[UUID]] = None
    mcp_group_ids: Optional[List[UUID]] = None
    skill_ids: Optional[List[UUID]] = None
    is_orchestrator: Optional[bool] = None
    is_planner: Optional[bool] = None
    emotional_profile_id: Optional[UUID] = None
    emotional_intensity: Optional[str] = None
    output_schema: Optional[Dict[str, Any]] = None
    input_schema: Optional[Dict[str, Any]] = None
    transition_output_schema: Optional[Dict[str, Any]] = None
    transition_input_schema: Optional[Dict[str, Any]] = None
    vector_memory_enabled: Optional[bool] = None
    training_memory_enabled: Optional[bool] = None
    status_updates_enabled: Optional[bool] = None
    status_updates_config: Optional[Dict[str, Any]] = None
    planner_prompt: Optional[str] = None
    planner_model: Optional[str] = None
    is_guardrail_active: Optional[bool] = None
    guardrail_prompt: Optional[str] = None
    guardrail_model: Optional[str] = None
    trigger_keywords: Optional[List[str]] = None
    entity_memory_path: Optional[str] = None


class AgentResponse(BaseModel):
    """Schema for agent response"""
    id: UUID
    name: str
    description: Optional[str] = None
    system_prompt: str = ""
    model: str = "gpt-4o-mini"
    temperature: str = "0.7"
    max_tokens: str = "2000"
    config: Dict[str, Any] = {}
    is_active: bool = True
    access_level: AccessLevelEnum = AccessLevelEnum.NORMAL
    collaboration_enabled: bool = True
    is_orchestrator: bool = False
    is_planner: bool = False
    emotional_profile: Optional[EmotionalProfileSummary] = None
    emotional_intensity: str = "medium"
    output_schema: Optional[Dict[str, Any]] = None
    input_schema: Optional[Dict[str, Any]] = None
    transition_output_schema: Optional[Dict[str, Any]] = None
    transition_input_schema: Optional[Dict[str, Any]] = None
    vector_memory_enabled: bool = False
    training_memory_enabled: bool = False
    status_updates_enabled: bool = False
    status_updates_config: Optional[Dict[str, Any]] = None
    planner_prompt: Optional[str] = None
    planner_model: Optional[str] = None
    is_guardrail_active: bool = False
    guardrail_prompt: Optional[str] = None
    guardrail_model: Optional[str] = None
    trigger_keywords: List[str] = []
    entity_memory_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    mcps: List[MCPSummary] = []
    mcp_groups: List[MCPGroupSummary] = []
    skills: List[SkillSummary] = []
    collaborators: List[CollaboratorSummary] = []

    model_config = ConfigDict(from_attributes=True)


class AgentListItem(BaseModel):
    """Schema for agent in list"""
    id: UUID
    name: str
    description: Optional[str]
    is_active: bool
    access_level: AccessLevelEnum = AccessLevelEnum.NORMAL
    collaboration_enabled: bool = True
    is_orchestrator: bool = False
    is_planner: bool = False
    emotional_profile_id: Optional[UUID] = None
    vector_memory_enabled: bool = False
    training_memory_enabled: bool = False
    mcp_count: int = 0
    collaborator_count: int = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentList(BaseModel):
    """Schema for list of agents"""
    agents: List[AgentListItem]
    total: int
