from pydantic import BaseModel, Field, UUID4
from typing import Optional, List
from datetime import datetime


class AgentGroupBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    is_active: bool = True
    parent_id: Optional[UUID4] = None


class AgentGroupCreate(AgentGroupBase):
    pass


class AgentGroupUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    parent_id: Optional[UUID4] = None


class AgentGroupResponse(AgentGroupBase):
    id: UUID4
    created_at: datetime
    updated_at: datetime
    agent_count: int = 0
    children_count: int = 0

    model_config = {"from_attributes": True}


class AgentGroupTree(AgentGroupResponse):
    """Recursive tree node with children"""
    children: List["AgentGroupTree"] = []

    model_config = {"from_attributes": True}
