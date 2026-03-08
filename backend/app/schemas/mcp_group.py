from pydantic import BaseModel, Field, UUID4
from typing import Optional, List, Any
from datetime import datetime

class MCPGroupBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    is_active: bool = True

class MCPGroupCreate(MCPGroupBase):
    pass

class MCPGroupUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None

class MCPGroupResponse(MCPGroupBase):
    id: UUID4
    created_at: datetime
    updated_at: datetime
    
    # Can contain `mcps` array dynamically
    # mcps: Optional[List[Any]] = None

    class Config:
        from_attributes = True
