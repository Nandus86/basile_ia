"""
VFS Knowledge Base Models - RAG 3.0
Stores knowledge bases and their .md files in a Virtual File System
"""
from sqlalchemy import Column, String, Boolean, DateTime, Text, Integer, ForeignKey, Table
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.database import Base


# Association table for agents <-> vfs_knowledge_bases (many-to-many)
agent_vfs_knowledge_base_access = Table(
    "agent_vfs_knowledge_base_access",
    Base.metadata,
    Column("agent_id", UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
    Column("knowledge_base_id", UUID(as_uuid=True), ForeignKey("vfs_knowledge_bases.id", ondelete="CASCADE"), primary_key=True)
)


class VFSKnowledgeBase(Base):
    """A collection of .md files used for RAG 3.0 subagent retrieval"""
    __tablename__ = "vfs_knowledge_bases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    vfs_path = Column(String(500), nullable=False)  # Local filesystem directory path
    file_count = Column(Integer, default=0)
    total_size_bytes = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    files = relationship(
        "VFSFile",
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    agents = relationship(
        "Agent",
        secondary=agent_vfs_knowledge_base_access,
        back_populates="vfs_knowledge_bases",
        lazy="selectin"
    )

    def __repr__(self):
        return f"<VFSKnowledgeBase {self.name} ({self.file_count} files)>"


class VFSFile(Base):
    """Individual .md file within a VFS Knowledge Base"""
    __tablename__ = "vfs_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_base_id = Column(UUID(as_uuid=True), ForeignKey("vfs_knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    title = Column(String(500), nullable=True)
    file_path = Column(String(500), nullable=False)
    size_bytes = Column(Integer, default=0)
    summary = Column(Text, nullable=True)  # Auto-generated summary

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    knowledge_base = relationship("VFSKnowledgeBase", back_populates="files")

    def __repr__(self):
        return f"<VFSFile {self.filename}>"
