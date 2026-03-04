"""
AI Provider Model - Configuration for different LLM providers
"""
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid

from app.database import Base


class AIProvider(Base):
    """Configuration for an AI Provider (e.g. OpenAI, OpenRouter, Anthropic)"""
    __tablename__ = "ai_providers"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True, index=True) # e.g., 'openai', 'openrouter', 'anthropic'
    base_url = Column(String(255), nullable=True) # Optional custom base URL
    api_key = Column(String(500), nullable=False) # The API Key/Token
    default_model = Column(String(100), nullable=True) # Default model used if not specified by agent
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<AIProvider {self.name} (active={self.is_active})>"
