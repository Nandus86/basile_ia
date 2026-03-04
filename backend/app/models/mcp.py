"""
MCP (Model Context Protocol) Model
"""
from sqlalchemy import Column, String, Boolean, DateTime, Text, JSON, Enum, Integer
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid
import enum

from app.database import Base


class MCPProtocol(str, enum.Enum):
    """Protocol types for MCP connections"""
    HTTP = "http"          # Standard HTTP request/response
    SSE = "sse"            # Server-Sent Events
    WEBSOCKET = "websocket"  # WebSocket connection
    STDIO = "stdio"        # Standard I/O (for local tools)


class MCP(Base):
    """MCP Tool/Action model"""
    __tablename__ = "mcps"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    endpoint = Column(String(500), nullable=False)
    method = Column(String(10), default="POST")
    protocol = Column(String(20), default="http")  # http, sse, websocket, stdio
    headers = Column(JSON, default=dict)
    body_template = Column(JSON, default=dict)
    response_mapping = Column(JSON, default=dict)
    trigger_keywords = Column(JSON, default=list)
    timeout_seconds = Column(Integer, default=30)  # Timeout for requests
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    def __repr__(self):
        return f"<MCP {self.name}>"
