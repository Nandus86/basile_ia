from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class ContactItem(BaseModel):
    number: str
    name: str

class SystemInfo(BaseModel):
    apikey: Optional[str] = None
    model_config = {"extra": "allow"}

class DispatchPayload(BaseModel):
    type_id: str
    queue_id: str
    service_id: str
    contacts: List[ContactItem]
    message: str
    timestamp_create: str
    callback_url: str
    context_data: Optional[Dict[str, Any]] = None
    transition_data: Optional[Dict[str, Any]] = None
    system: SystemInfo

    model_config = {"extra": "allow"}

class DispatchAcceptedResponse(BaseModel):
    service_id: str
    campaign_key: str
    run_id: str
    queued_count: int
    status: str = "accepted"

class CampaignStatus(BaseModel):
    service_id: str
    status: str  # running | paused | completed | failed
    total: int
    sent: int
    failed: int
    percent: float
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

class CampaignReport(CampaignStatus):
    success_rate: float
    total_duration_seconds: Optional[float] = None
    dlq_count: int
    config_id: Optional[str] = None
    config_path: Optional[str] = None
    avg_delay_seconds: Optional[float] = None
