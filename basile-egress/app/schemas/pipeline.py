"""
Egress Pipeline Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID


class EgressPipelineBase(BaseModel):
    name: str
    path: str
    is_active: bool = True
    description: Optional[str] = None
    output_url: str
    output_method: str = "POST"
    output_schema: Optional[Dict[str, Any]] = None
    output_headers: Optional[Dict[str, Any]] = None
    retry_config: Optional[Dict[str, Any]] = Field(default={"maxRetries": 3, "delays": [5000, 15000, 60000]})


class EgressPipelineCreate(EgressPipelineBase):
    pass


class EgressPipelineUpdate(EgressPipelineBase):
    name: Optional[str] = None
    path: Optional[str] = None
    output_url: Optional[str] = None


class EgressPipelineResponse(EgressPipelineBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EgressPipelineListResponse(BaseModel):
    pipelines: List[EgressPipelineResponse]
    total: int
