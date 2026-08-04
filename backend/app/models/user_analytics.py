from sqlalchemy import Column, String, Integer, DateTime, Float, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime, timezone
import uuid

from app.database import Base

class UserAnalytics(Base):
    """
    Analytics profile for a user - flexible schema using JSONB.
    This tracks engagement and learned behavior over time without rigid migrations.
    """
    __tablename__ = "user_analytics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String(255), unique=True, nullable=False, index=True)
    church_id = Column(String(255), nullable=True, index=True)
    
    # Indexed fields for fast querying
    interaction_count = Column(Integer, default=0, nullable=False)
    engagement_score = Column(Float, default=0.0, nullable=False)  # 0 to 100
    care_priority = Column(String(20), default="low", nullable=False)  # low/medium/high/critical
    
    first_seen_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_analyzed_at = Column(DateTime(timezone=True), nullable=True) # Para controle do Agente Analista (rodar 1x ao dia)
    
    # The heart of the model: flexible JSONB data
    # Zones: __zona_crm, __zona_aprendizado, __zona_metricas
    profile_data = Column(JSONB, default=dict, nullable=False)
    
    # Audit timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<UserAnalytics session={self.session_id} | score={self.engagement_score} | priority={self.care_priority}>"
