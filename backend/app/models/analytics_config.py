from sqlalchemy import Column, String, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid

from app.database import Base

class AnalyticsConfig(Base):
    """
    Configuration for the Analytics Agent scheduler and Data Mapping.
    """
    __tablename__ = "analytics_config"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(String, nullable=True) # ID of the chosen Analyst Agent
    cron_time = Column(String, default="03:00") # Format HH:MM
    is_active = Column(Boolean, default=True)
    crm_mapping = Column(JSONB, default=list)
    metrics_mapping = Column(JSONB, default=list)

    def __repr__(self):
        return f"<AnalyticsConfig agent={self.agent_id} time={self.cron_time}>"
