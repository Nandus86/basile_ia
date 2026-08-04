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
