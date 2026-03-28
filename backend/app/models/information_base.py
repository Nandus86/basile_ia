from sqlalchemy import Column, String, Boolean, Integer, Table, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.database import Base


# Association table for Many-to-Many relationship between Agents and Information Bases
agent_info_base_access = Table(
    "agent_info_base_access",
    Base.metadata,
    Column("agent_id", PG_UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
    Column("information_base_id", PG_UUID(as_uuid=True), ForeignKey("information_bases.id", ondelete="CASCADE"), primary_key=True)
)


class InformationBase(Base):
    """
    Model representing an Information Base.
    Used for creating customizable vector document sources that agents can use for RAG filtering by user IDs.
    """
    __tablename__ = "information_bases"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    code = Column(String(100), nullable=False, unique=True, index=True)
    content_schema = Column(JSONB, nullable=True)
    metadata_schema = Column(JSONB, nullable=True)
    correlation_schema = Column(JSONB, nullable=True) # Novo Schema para correlacionar o contexto com o "id"
    max_results = Column(Integer, nullable=False, server_default="3") # Máximo de resultados por busca
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    agents = relationship("Agent", secondary=agent_info_base_access, back_populates="information_bases")
