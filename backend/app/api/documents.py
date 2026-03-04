"""
Documents API - Knowledge Base Management
"""
import os
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Optional, List
from uuid import UUID
from datetime import datetime, timezone

from app.database import get_db
from app.models.document import Document
from app.models.agent import Agent
from app.schemas.document import (
    DocumentCreate, DocumentUpdate, DocumentResponse, DocumentSummary,
    DocumentList, DocumentSearchRequest, DocumentSearchResult, UploadResponse
)
from app.services.document_processor import get_document_processor, UPLOAD_DIR

router = APIRouter()


async def process_document_background(
    document_id: str,
    file_path: str,
    file_type: str,
    document_name: str,
    chunk_size: int,
    chunk_overlap: int
):
    """Background task to process document"""
    from app.database import async_session_maker
    from app.models.document import Document
    
    processor = get_document_processor()
    
    async with async_session_maker() as db:
        # Update status to processing
        result = await db.execute(select(Document).where(Document.id == UUID(document_id)))
        doc = result.scalar_one_or_none()
        
        if not doc:
            return
        
        doc.status = "processing"
        await db.commit()
        
        # Process
        process_result = await processor.process_document(
            document_id=document_id,
            file_path=file_path,
            file_type=file_type,
            document_name=document_name,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            metadata={"original_filename": doc.original_filename}
        )
        
        # Update document
        if process_result["success"]:
            doc.status = "ready"
            doc.chunk_count = process_result["chunk_count"]
            doc.content_hash = process_result.get("content_hash")
            doc.processed_at = datetime.now(timezone.utc)
            doc.error_message = None
        else:
            doc.status = "error"
            doc.error_message = process_result.get("error", "Unknown error")
        
        await db.commit()


@router.get("", response_model=DocumentList)
async def list_documents(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    is_global: Optional[bool] = None,
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db)
):
    """List all documents"""
    query = select(Document).order_by(Document.created_at.desc())
    
    if status is not None:
        query = query.where(Document.status == status)
    if is_global is not None:
        query = query.where(Document.is_global == is_global)
    if is_active is not None:
        query = query.where(Document.is_active == is_active)
    
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    documents = result.scalars().all()
    
    # Count total
    count_query = select(Document)
    if status is not None:
        count_query = count_query.where(Document.status == status)
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())
    
    return DocumentList(
        documents=[DocumentSummary(
            id=doc.id,
            name=doc.name,
            file_type=doc.file_type,
            status=doc.status,
            chunk_count=doc.chunk_count,
            is_global=doc.is_global,
            is_active=doc.is_active,
            created_at=doc.created_at
        ) for doc in documents],
        total=total
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    chunk_size: int = Form(1000),
    chunk_overlap: int = Form(200),
    is_global: bool = Form(False),
    db: AsyncSession = Depends(get_db)
):
    """Upload and process a document"""
    # Validate file type
    filename = file.filename or "unknown"
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"
    
    allowed_types = ["pdf", "txt", "md", "markdown", "docx", "html", "json", "csv"]
    if extension not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed: {', '.join(allowed_types)}"
        )
    
    # Create upload directory if needed
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    import uuid
    doc_id = uuid.uuid4()
    safe_filename = f"{doc_id}_{filename}"
    file_path = UPLOAD_DIR / safe_filename
    
    # Save file
    try:
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
            file_size = len(content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}"
        )
    
    # Create document record
    doc_name = name or filename.rsplit(".", 1)[0]
    
    document = Document(
        id=doc_id,
        name=doc_name,
        description=description,
        file_path=str(file_path),
        original_filename=filename,
        file_type=extension,
        file_size_bytes=file_size,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        is_global=is_global,
        status="pending"
    )
    
    db.add(document)
    await db.commit()
    await db.refresh(document)
    
    # Start background processing
    background_tasks.add_task(
        process_document_background,
        document_id=str(document.id),
        file_path=str(file_path),
        file_type=extension,
        document_name=doc_name,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
    )
    
    return UploadResponse(
        success=True,
        document_id=document.id,
        message="Document uploaded and processing started",
        file_name=filename
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get document details"""
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return document


@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: UUID,
    update: DocumentUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update document metadata"""
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(document, field, value)
    
    await db.commit()
    await db.refresh(document)
    
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete a document and its chunks"""
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Delete chunks from Weaviate
    processor = get_document_processor()
    await processor.delete_document_chunks(str(document_id))
    
    # Delete file
    if os.path.exists(document.file_path):
        os.remove(document.file_path)
    
    # Delete record
    await db.delete(document)
    await db.commit()


@router.post("/{document_id}/reprocess", response_model=UploadResponse)
async def reprocess_document(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Reprocess a document"""
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if not os.path.exists(document.file_path):
        raise HTTPException(status_code=400, detail="Source file not found")
    
    # Delete old chunks
    processor = get_document_processor()
    await processor.delete_document_chunks(str(document_id))
    
    # Update status
    document.status = "reprocessing"
    document.chunk_count = 0
    await db.commit()
    
    # Start reprocessing
    background_tasks.add_task(
        process_document_background,
        document_id=str(document.id),
        file_path=document.file_path,
        file_type=document.file_type,
        document_name=document.name,
        chunk_size=document.chunk_size,
        chunk_overlap=document.chunk_overlap
    )
    
    return UploadResponse(
        success=True,
        document_id=document.id,
        message="Document reprocessing started",
        file_name=document.original_filename
    )


@router.post("/search")
async def search_documents(
    request: DocumentSearchRequest,
    db: AsyncSession = Depends(get_db)
):
    """Search documents for relevant content"""
    processor = get_document_processor()
    
    document_ids = [str(id) for id in request.document_ids] if request.document_ids else None
    
    results = await processor.search(
        query=request.query,
        limit=request.limit,
        document_ids=document_ids
    )
    
    return {
        "query": request.query,
        "results": results,
        "total": len(results)
    }
