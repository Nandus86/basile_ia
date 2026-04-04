"""
Workflow Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime

class WorkflowBase(BaseModel):
    name: str = Field(..., description="Name of the workflow")
    description: Optional[str] = Field(None, description="Detailed description")
    is_active: bool = True
    definition: Dict[str, Any] = Field(default_factory=dict, description="Vue Flow JSON representing nodes and edges")

class WorkflowCreate(WorkflowBase):
    pass

class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    definition: Optional[Dict[str, Any]] = None

class WorkflowResponse(WorkflowBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class WorkflowList(BaseModel):
    workflows: List[WorkflowResponse]
    total: int
