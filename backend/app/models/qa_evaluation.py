"""
QAEvaluation model — Q&A Eval System
Stores human annotations/evaluations of conversation pairs for training data curation.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.database import Base


class QAEvaluation(Base):
    __tablename__ = "qa_evaluations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(UUID(as_uuid=True), ForeignKey("conversation_messages.id", ondelete="CASCADE"), nullable=False)
    pair_message_id = Column(UUID(as_uuid=True), ForeignKey("conversation_messages.id", ondelete="SET NULL"), nullable=True)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(String, nullable=False)

    # Classification: "relevant" | "indifferent" | "irrelevant"
    classification = Column(String(20), nullable=False, default="indifferent")
    # Score: 0-100
    score = Column(Integer, nullable=True)
    # Topic/category
    topic = Column(String(200), nullable=True)
    # Expected response (when AI was wrong)
    expected_response = Column(Text, nullable=True)
    # Tool usage instruction (how agent should use tools)
    tool_instruction = Column(Text, nullable=True)

    # Snapshots of original content (so data persists even if messages are deleted)
    original_question = Column(Text, nullable=False)
    original_answer = Column(Text, nullable=False)
    # Snapshot of tool trace from the message
    tool_trace = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_qa_eval_agent", "agent_id"),
        Index("idx_qa_eval_session", "session_id"),
        Index("idx_qa_eval_classification", "classification"),
        Index("idx_qa_eval_score", "score"),
        Index("idx_qa_eval_topic", "topic"),
        Index("idx_qa_eval_message", "message_id", unique=True),
    )

    def __repr__(self):
        return f"<QAEvaluation {self.classification} score={self.score} @ {self.created_at}>"
