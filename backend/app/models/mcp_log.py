from sqlalchemy import Column, String, Integer, DateTime, JSON, Float
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
import uuid
from datetime import datetime
from app.database import Base

class MCPExecutionLog(Base):
    __tablename__ = "mcp_execution_logs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    mcp_id = Column(PG_UUID(as_uuid=True), nullable=True, index=True)
    mcp_name = Column(String, nullable=True)
    protocol = Column(String, nullable=True)
    endpoint = Column(String, nullable=True)
    request_params = Column(JSON, nullable=True)
    response_data = Column(JSON, nullable=True)
    status = Column(String, nullable=True)  # 'success', 'failed'
    error_message = Column(String, nullable=True)
    duration_ms = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
