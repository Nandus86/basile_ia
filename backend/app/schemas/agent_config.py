"""
Agent Configuration Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class AgentConfigBase(BaseModel):
    """Base configuration schema"""
    # Retry Configuration
    max_retries: int = Field(default=3, ge=0, le=10, description="Maximum retry attempts")
    retry_delay_seconds: float = Field(default=1.0, ge=0, description="Delay between retries")
    retry_exponential_backoff: bool = Field(default=True, description="Use exponential backoff")
    
    # Timeout
    timeout_seconds: int = Field(default=120, ge=1, le=600, description="Request timeout")
    
    # Fallback
    fallback_enabled: bool = Field(default=False, description="Enable fallback model")
    fallback_model: str = Field(default="gpt-4o-mini", description="Fallback model name")
    fallback_temperature: float = Field(default=0.7, ge=0, le=2)
    
    # Checkpoints
    checkpoint_enabled: bool = Field(default=False, description="Enable state checkpoints")
    checkpoint_storage: str = Field(default="memory", description="Storage: memory, redis, postgres")
    checkpoint_ttl_seconds: int = Field(default=3600, ge=60, description="Checkpoint TTL")
    
    # Human in the loop
    human_approval_enabled: bool = Field(default=False, description="Require human approval")
    human_approval_timeout_seconds: int = Field(default=300, ge=30, description="Approval timeout")
    interrupt_before_nodes: List[str] = Field(default_factory=list, description="Nodes to pause before")
    interrupt_after_nodes: List[str] = Field(default_factory=list, description="Nodes to pause after")
    require_approval_for: List[str] = Field(default_factory=list, description="Actions requiring approval: tool_call, mcp_execution")
    
    # Rate limiting
    rate_limit_enabled: bool = Field(default=False)
    max_requests_per_minute: int = Field(default=60, ge=1)
    
    # Logging
    verbose_logging: bool = Field(default=False)
    log_tool_calls: bool = Field(default=True)


class AgentConfigCreate(AgentConfigBase):
    """Schema for creating agent config"""
    pass


class AgentConfigUpdate(BaseModel):
    """Schema for updating agent config (all fields optional)"""
    max_retries: Optional[int] = None
    retry_delay_seconds: Optional[float] = None
    retry_exponential_backoff: Optional[bool] = None
    timeout_seconds: Optional[int] = None
    fallback_enabled: Optional[bool] = None
    fallback_model: Optional[str] = None
    fallback_temperature: Optional[float] = None
    checkpoint_enabled: Optional[bool] = None
    checkpoint_storage: Optional[str] = None
    checkpoint_ttl_seconds: Optional[int] = None
    human_approval_enabled: Optional[bool] = None
    human_approval_timeout_seconds: Optional[int] = None
    interrupt_before_nodes: Optional[List[str]] = None
    interrupt_after_nodes: Optional[List[str]] = None
    require_approval_for: Optional[List[str]] = None
    rate_limit_enabled: Optional[bool] = None
    max_requests_per_minute: Optional[int] = None
    verbose_logging: Optional[bool] = None
    log_tool_calls: Optional[bool] = None


class AgentConfigResponse(AgentConfigBase):
    """Schema for config response"""
    id: UUID
    agent_id: UUID
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class PendingApprovalResponse(BaseModel):
    """Schema for pending approval"""
    id: UUID
    agent_id: UUID
    session_id: str
    action_type: str
    action_name: Optional[str]
    action_data: Optional[dict]
    message: Optional[str]
    status: str
    created_at: datetime
    expires_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class ApprovalAction(BaseModel):
    """Schema for approval/rejection"""
    approved: bool
    note: Optional[str] = None
    approved_by: Optional[str] = None
