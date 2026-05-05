"""
Workflow Execution Model - Tracks each execution of a workflow pipeline
"""
from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.database import Base


class WorkflowExecution(Base):
    """Tracks each execution of a workflow"""
    __tablename__ = "workflow_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True)

    status = Column(String(50), default="pending", nullable=False)  # pending, running, completed, failed, cancelled
    trigger_type = Column(String(50), nullable=True)  # webhook, manual, schedule, event
    trigger_data = Column(JSON, nullable=True)  # incoming payload

    # Execution state
    context = Column(JSON, default=dict, nullable=False)  # accumulated workflow_context
    current_block_id = Column(String(255), nullable=True)  # block currently executing
    blocks_executed = Column(JSON, default=list, nullable=False)  # list of {block_id, status, duration_ms, output_key, error}
    blocks_total = Column(Integer, default=0)

    # Result
    result = Column(JSON, nullable=True)  # final output of the workflow
    error_message = Column(Text, nullable=True)

    # Timing
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    workflow = relationship("Workflow", backref="executions", lazy="selectin")

    def __repr__(self):
        return f"<WorkflowExecution {self.id} | workflow={self.workflow_id} | status={self.status}>"
