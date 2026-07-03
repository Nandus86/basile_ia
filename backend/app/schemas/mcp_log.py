from pydantic import BaseModel, ConfigDict
from typing import Optional, Any, Dict, List
from uuid import UUID
from datetime import datetime

class MCPExecutionLogBase(BaseModel):
    mcp_id: Optional[UUID] = None
    mcp_name: Optional[str] = None
    protocol: Optional[str] = None
    endpoint: Optional[str] = None
    request_params: Optional[Dict[str, Any]] = None
    response_data: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    error_message: Optional[str] = None
    duration_ms: Optional[float] = None

class MCPExecutionLogCreate(MCPExecutionLogBase):
    pass

class MCPExecutionLogResponse(MCPExecutionLogBase):
    id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class MCPExecutionLogList(BaseModel):
    items: List[MCPExecutionLogResponse]
    total: int
