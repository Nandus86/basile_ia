"""
ConversationMessage model — Medium-Term Memory (MTM)
Stores complete conversation history in PostgreSQL for persistent tracking.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(String, nullable=False)
    role = Column(String(20), nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_conv_msg_agent_session", "agent_id", "session_id", "created_at"),
        Index("idx_conv_msg_session", "session_id", "created_at"),
    )

    def __repr__(self):
        return f"<ConversationMessage {self.role} @ {self.created_at}>"
