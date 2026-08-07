from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID

class UserAnalyticsBase(BaseModel):
    session_id: str
    church_id: Optional[str] = None
    interaction_count: int = 0
    engagement_score: float = 0.0
    care_priority: str = "low"
    profile_data: Dict[str, Any] = Field(default_factory=dict)

class UserAnalyticsCreate(UserAnalyticsBase):
    pass

class UserAnalyticsUpdate(BaseModel):
    interaction_count: Optional[int] = None
    engagement_score: Optional[float] = None
    care_priority: Optional[str] = None
    profile_data: Optional[Dict[str, Any]] = None
    last_seen_at: Optional[datetime] = None
    last_analyzed_at: Optional[datetime] = None

class UserAnalyticsResponse(UserAnalyticsBase):
    id: UUID
    first_seen_at: datetime
    last_seen_at: datetime
    last_analyzed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class AnalyticsListResponse(BaseModel):
    users: List[UserAnalyticsResponse]
    total: int
    skip: int
    limit: int

class AnalyticsConfigUpdate(BaseModel):
    agent_id: Optional[str] = None
    church_agent_id: Optional[str] = None
    system_agent_id: Optional[str] = None
    cron_time: Optional[str] = None
    church_report_time: Optional[str] = None
    system_report_time: Optional[str] = None
    is_active: Optional[bool] = None
    crm_mapping: Optional[List[Dict[str, Any]]] = None
    metrics_mapping: Optional[List[Dict[str, Any]]] = None

class AnalyticsConfigResponse(BaseModel):
    id: UUID
    agent_id: Optional[str] = None
    church_agent_id: Optional[str] = None
    system_agent_id: Optional[str] = None
    cron_time: str
    church_report_time: str
    system_report_time: str
    is_active: bool
    crm_mapping: List[Dict[str, Any]]
    metrics_mapping: List[Dict[str, Any]]

    model_config = {"from_attributes": True}

class AnalyticsReportResponse(BaseModel):
    id: UUID
    level: str
    period_type: str
    entity_id: str
    entity_name: Optional[str] = None
    period_start: datetime
    period_end: datetime
    stats: Dict[str, Any]
    report_content: Optional[str] = None
    agent_id: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

class AnalyticsReportListResponse(BaseModel):
    reports: List[AnalyticsReportResponse]
    total: int
    skip: int
    limit: int
