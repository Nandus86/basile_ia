from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime, timezone
import uuid

from app.database import Base

class AnalyticsReport(Base):
    """
    Stores generated analytical reports (daily, weekly, monthly) for users, churches, and the system.
    """
    __tablename__ = "analytics_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    level = Column(String(20), nullable=False)           # 'user', 'church', 'system'
    period_type = Column(String(20), nullable=False)     # 'daily', 'weekly', 'monthly'
    entity_id = Column(String(255), nullable=False)      # session_id, church_id, or 'system'
    entity_name = Column(String(255), nullable=True)     # Human readable name
    
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    
    # Quantitative data
    stats = Column(JSONB, default=dict)
    
    # Qualitative data (from LLM Map-Reduce)
    report_content = Column(Text, nullable=True)
    sub_reports = Column(JSONB, default=list)            # The input blocks used to generate this report
    
    agent_id = Column(String(255), nullable=True)
    status = Column(String(20), default="pending")       # 'pending', 'processing', 'completed', 'failed'
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<AnalyticsReport {self.level} | {self.period_type} | {self.entity_id}>"
