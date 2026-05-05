"""
Workflow Execution Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime


class BlockExecutionDetail(BaseModel):
    """Detail of a single block execution within a workflow run"""
    block_id: str
    block_type: str
    label: str = ""
    status: str  # success, failed, skipped
    output_key: Optional[str] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None


class WorkflowExecuteRequest(BaseModel):
    """Request to execute a workflow manually"""
    trigger_data: Dict[str, Any] = Field(default_factory=dict, description="Payload to inject as $trigger.payload")
    async_mode: bool = Field(default=False, description="If true, execute in background and return immediately")


class WorkflowTestBlockRequest(BaseModel):
    """Request to test a single block in isolation"""
    block: Dict[str, Any] = Field(..., description="Block definition to test")
    context: Dict[str, Any] = Field(default_factory=dict, description="Simulated workflow_context")


class WorkflowTestBlockResponse(BaseModel):
    """Response from testing a single block"""
    success: bool
    output_key: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None


class WorkflowExecutionResponse(BaseModel):
    """Response for a workflow execution"""
    id: UUID
    workflow_id: UUID
    status: str
    trigger_type: Optional[str] = None
    trigger_data: Optional[Dict[str, Any]] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    current_block_id: Optional[str] = None
    blocks_executed: List[Dict[str, Any]] = Field(default_factory=list)
    blocks_total: int = 0
    result: Optional[Any] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class WorkflowExecutionList(BaseModel):
    """List of workflow executions"""
    executions: List[WorkflowExecutionResponse]
    total: int
