"""
MCP Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID
from enum import Enum


class MCPProtocolEnum(str, Enum):
    """Protocol types for MCP connections"""
    HTTP = "http"
    SSE = "sse"
    MCP = "mcp"  # Full Model Context Protocol (bidirectional)
    WEBSOCKET = "websocket"
    STDIO = "stdio"


class MCPBase(BaseModel):
    """Base MCP schema"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    endpoint: str = Field(..., min_length=1)
    method: str = Field(default="POST")
    protocol: str = Field(default="http", description="Protocol: http, sse, websocket, stdio")
    headers: Dict[str, str] = Field(default_factory=dict)
    body_template: Dict[str, Any] = Field(default_factory=dict)
    query_template: Dict[str, Any] = Field(default_factory=dict)
    response_mapping: Dict[str, str] = Field(default_factory=dict)
    trigger_keywords: List[str] = Field(default_factory=list)
    timeout_seconds: int = Field(default=30, description="Timeout in seconds")
    is_active: bool = True
    group_id: Optional[UUID] = None


class MCPCreate(MCPBase):
    """Schema for creating an MCP"""
    pass


class MCPUpdate(BaseModel):
    """Schema for updating an MCP"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    endpoint: Optional[str] = None
    method: Optional[str] = None
    protocol: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    body_template: Optional[Dict[str, Any]] = None
    query_template: Optional[Dict[str, Any]] = None
    response_mapping: Optional[Dict[str, str]] = None
    trigger_keywords: Optional[List[str]] = None
    timeout_seconds: Optional[int] = None
    is_active: Optional[bool] = None
    group_id: Optional[UUID] = None


class MCPResponse(MCPBase):
    """Schema for MCP response"""
    id: UUID
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class MCPList(BaseModel):
    """Schema for list of MCPs"""
    mcps: List[MCPResponse]
    total: int


class MCPExecuteRequest(BaseModel):
    """Schema for executing an MCP"""
    params: Dict[str, Any] = Field(default_factory=dict)
    stream: bool = Field(default=False, description="Whether to stream SSE responses")


class MCPExecuteResponse(BaseModel):
    """Schema for MCP execution response"""
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    execution_time_ms: float
    events: Optional[List[Dict[str, Any]]] = None  # For SSE events
