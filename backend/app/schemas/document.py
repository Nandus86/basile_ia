"""
Document Schemas for Knowledge Base
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from enum import Enum


class DocumentStatusEnum(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"
    REPROCESSING = "reprocessing"


class DocumentTypeEnum(str, Enum):
    PDF = "pdf"
    TXT = "txt"
    MARKDOWN = "markdown"
    DOCX = "docx"
    HTML = "html"
    JSON = "json"
    CSV = "csv"


class DocumentBase(BaseModel):
    """Base document schema"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    chunk_size: int = Field(default=1000, ge=100, le=4000, description="Characters per chunk")
    chunk_overlap: int = Field(default=200, ge=0, le=1000, description="Overlap between chunks")
    is_global: bool = Field(default=False, description="Available to all agents")
    tags: List[str] = Field(default_factory=list)
    doc_metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentCreate(DocumentBase):
    """Schema for creating document (upload)"""
    pass


class DocumentUpdate(BaseModel):
    """Schema for updating document"""
    name: Optional[str] = None
    description: Optional[str] = None
    is_global: Optional[bool] = None
    tags: Optional[List[str]] = None
    doc_metadata: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class DocumentResponse(DocumentBase):
    """Full document response"""
    id: UUID
    file_path: str
    original_filename: str
    file_type: str
    file_size_bytes: int
    content_hash: Optional[str]
    weaviate_class: str
    chunk_count: int
    embedding_model: str
    status: str
    error_message: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    processed_at: Optional[datetime]
    
    model_config = {"from_attributes": True}


class DocumentSummary(BaseModel):
    """Summary for listing"""
    id: UUID
    name: str
    file_type: str
    status: str
    chunk_count: int
    is_global: bool
    is_active: bool
    created_at: datetime
    
    model_config = {"from_attributes": True}


class DocumentList(BaseModel):
    """List response"""
    documents: List[DocumentSummary]
    total: int


class DocumentChunk(BaseModel):
    """Document chunk info"""
    index: int
    content: str
    metadata: Dict[str, Any]
    

class DocumentSearchResult(BaseModel):
    """Search result from vector store"""
    document_id: str
    document_name: str
    chunk_index: int
    content: str
    score: float
    metadata: Dict[str, Any]


class DocumentSearchRequest(BaseModel):
    """Search request"""
    query: str
    limit: int = Field(default=5, ge=1, le=20)
    document_ids: Optional[List[UUID]] = None  # Filter by specific documents


class UploadResponse(BaseModel):
    """Upload response"""
    success: bool
    document_id: Optional[UUID] = None
    message: str
    file_name: Optional[str] = None
