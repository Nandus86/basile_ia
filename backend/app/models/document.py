"""
Document Model for Knowledge Base
Stores documents and their vectorized chunks in Weaviate
"""
from sqlalchemy import Column, String, Boolean, DateTime, Text, JSON, Integer, ForeignKey, Table, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid
import enum

from app.database import Base


# Association table for agents <-> documents (many-to-many)
agent_document_access = Table(
    "agent_document_access",
    Base.metadata,
    Column("agent_id", UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
    Column("document_id", UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
)


class DocumentStatus(str, enum.Enum):
    """Document processing status"""
    PENDING = "pending"          # Uploaded, waiting to process
    PROCESSING = "processing"    # Currently being chunked/embedded
    READY = "ready"              # Successfully indexed
    ERROR = "error"              # Processing failed
    REPROCESSING = "reprocessing"  # Being reprocessed


class DocumentType(str, enum.Enum):
    """Supported document types"""
    PDF = "pdf"
    TXT = "txt"
    MARKDOWN = "markdown"
    DOCX = "docx"
    HTML = "html"
    JSON = "json"
    CSV = "csv"


class Document(Base):
    """Document for knowledge base"""
    __tablename__ = "documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Basic info
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # File info
    file_path = Column(String(500), nullable=False)  # Storage path
    original_filename = Column(String(255), nullable=False)
    file_type = Column(String(20), default="txt")
    file_size_bytes = Column(Integer, default=0)
    content_hash = Column(String(64))  # SHA-256 for deduplication
    
    # Vector storage info
    weaviate_class = Column(String(100), default="AgentDocuments")
    chunk_count = Column(Integer, default=0)
    
    # Processing config
    chunk_size = Column(Integer, default=1000)  # Characters per chunk
    chunk_overlap = Column(Integer, default=200)
    embedding_model = Column(String(100), default="paraphrase-multilingual-MiniLM-L12-v2")
    
    # Status
    status = Column(String(20), default="pending")
    error_message = Column(Text, nullable=True)
    
    # Metadata (renamed from 'metadata' to avoid SQLAlchemy reserved name conflict)
    doc_metadata = Column(JSON, default=dict)  # Custom metadata
    tags = Column(JSON, default=list)  # Tags for filtering
    
    # Access control
    is_global = Column(Boolean, default=False)  # Available to all agents
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    processed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    agents = relationship(
        "Agent",
        secondary=agent_document_access,
        back_populates="documents",
        lazy="selectin"
    )
    
    def __repr__(self):
        return f"<Document {self.name} ({self.status})>"
    
    def to_summary(self):
        """Return summary for listing"""
        return {
            "id": str(self.id),
            "name": self.name,
            "file_type": self.file_type,
            "status": self.status,
            "chunk_count": self.chunk_count,
            "is_global": self.is_global,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
