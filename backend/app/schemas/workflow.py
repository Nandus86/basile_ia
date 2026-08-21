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
    trigger_keywords: Optional[List[str]] = Field(default_factory=list, description="Keywords that trigger this workflow")
    trigger_match_mode: str = Field(default="word", description="Matching mode: word, contains, phrase")
    always_run_on_startup: bool = Field(default=False, description="If true, workflow runs immediately at startup")
    return_direct_payload: bool = Field(default=False, description="If true, workflow results bypass LLM and are merged directly into API response")
    strict_mode: bool = Field(default=False, description="If true, locks conversation inside workflow, blocking AI agent until completion or cancellation")
    strict_fallback_message: Optional[str] = Field(None, description="Custom fallback message sent when an unhandled/invalid input is received in strict mode")
    strict_retry_message: Optional[str] = Field(None, description="Custom retry message sent on 1st error before re-initiating workflow in strict mode")
    strict_timeout_message: Optional[str] = Field(None, description="Custom timeout message sent when the workflow execution expires")
    strict_exit_keywords: Optional[List[str]] = Field(default_factory=lambda: ["sair", "cancelar", "menu", "parar", "encerrar"], description="Keywords that allow the user to escape/cancel a strict workflow")

class WorkflowCreate(WorkflowBase):
    pass

class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    definition: Optional[Dict[str, Any]] = None
    trigger_keywords: Optional[List[str]] = None
    trigger_match_mode: Optional[str] = None
    always_run_on_startup: Optional[bool] = None
    return_direct_payload: Optional[bool] = None
    strict_mode: Optional[bool] = None
    strict_fallback_message: Optional[str] = None
    strict_retry_message: Optional[str] = None
    strict_timeout_message: Optional[str] = None
    strict_exit_keywords: Optional[List[str]] = None

class WorkflowResponse(WorkflowBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class WorkflowList(BaseModel):
    workflows: List[WorkflowResponse]
    total: int
