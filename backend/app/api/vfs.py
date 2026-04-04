"""
VFS Knowledge Base API - RAG 3.0
CRUD for VFS knowledge bases and their .md files
"""
import os
import shutil
from pathlib import Path
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field

from app.database import get_db
from app.models.vfs_knowledge_base import VFSKnowledgeBase, VFSFile, agent_vfs_knowledge_base_access
from app.models.agent import Agent
from app.services.vfs_rag_service import get_vfs_root

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────

class VFSKnowledgeBaseCreate(BaseModel):
    name: str
    description: Optional[str] = None

class VFSKnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class VFSFileResponse(BaseModel):
    id: str
    filename: str
    title: Optional[str] = None
    size_bytes: int = 0
    summary: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"from_attributes": True}

class VFSKnowledgeBaseResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    file_count: int = 0
    total_size_bytes: int = 0
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    files: List[VFSFileResponse] = []

    model_config = {"from_attributes": True}

class VFSFileUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


# ── Knowledge Base CRUD ──────────────────────────────────

@router.get("", response_model=List[VFSKnowledgeBaseResponse])
async def list_knowledge_bases(db: AsyncSession = Depends(get_db)):
    """List all VFS knowledge bases"""
    result = await db.execute(
        select(VFSKnowledgeBase)
        .options(selectinload(VFSKnowledgeBase.files))
        .order_by(VFSKnowledgeBase.created_at.desc())
    )
    bases = result.scalars().all()

    return [
        VFSKnowledgeBaseResponse(
            id=str(kb.id),
            name=kb.name,
            description=kb.description,
            file_count=kb.file_count,
            total_size_bytes=kb.total_size_bytes,
            is_active=kb.is_active,
            created_at=kb.created_at.isoformat() if kb.created_at else None,
            updated_at=kb.updated_at.isoformat() if kb.updated_at else None,
            files=[
                VFSFileResponse(
                    id=str(f.id),
                    filename=f.filename,
                    title=f.title,
                    size_bytes=f.size_bytes,
                    summary=f.summary,
                    created_at=f.created_at.isoformat() if f.created_at else None,
                    updated_at=f.updated_at.isoformat() if f.updated_at else None,
                )
                for f in kb.files
            ]
        )
        for kb in bases
    ]


@router.post("", response_model=VFSKnowledgeBaseResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(data: VFSKnowledgeBaseCreate, db: AsyncSession = Depends(get_db)):
    """Create a new VFS knowledge base"""
    kb_id = uuid4()
    vfs_path = str(get_vfs_root() / str(kb_id))

    # Create directory
    os.makedirs(vfs_path, exist_ok=True)

    kb = VFSKnowledgeBase(
        id=kb_id,
        name=data.name,
        description=data.description,
        vfs_path=vfs_path,
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)

    return VFSKnowledgeBaseResponse(
        id=str(kb.id),
        name=kb.name,
        description=kb.description,
        file_count=0,
        total_size_bytes=0,
        is_active=kb.is_active,
        created_at=kb.created_at.isoformat() if kb.created_at else None,
        updated_at=kb.updated_at.isoformat() if kb.updated_at else None,
        files=[],
    )


@router.get("/{kb_id}", response_model=VFSKnowledgeBaseResponse)
async def get_knowledge_base(kb_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get a VFS knowledge base with its files"""
    result = await db.execute(
        select(VFSKnowledgeBase)
        .options(selectinload(VFSKnowledgeBase.files))
        .where(VFSKnowledgeBase.id == kb_id)
    )
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    return VFSKnowledgeBaseResponse(
        id=str(kb.id),
        name=kb.name,
        description=kb.description,
        file_count=kb.file_count,
        total_size_bytes=kb.total_size_bytes,
        is_active=kb.is_active,
        created_at=kb.created_at.isoformat() if kb.created_at else None,
        updated_at=kb.updated_at.isoformat() if kb.updated_at else None,
        files=[
            VFSFileResponse(
                id=str(f.id),
                filename=f.filename,
                title=f.title,
                size_bytes=f.size_bytes,
                summary=f.summary,
                created_at=f.created_at.isoformat() if f.created_at else None,
                updated_at=f.updated_at.isoformat() if f.updated_at else None,
            )
            for f in kb.files
        ]
    )


@router.put("/{kb_id}", response_model=VFSKnowledgeBaseResponse)
async def update_knowledge_base(kb_id: UUID, data: VFSKnowledgeBaseUpdate, db: AsyncSession = Depends(get_db)):
    """Update a VFS knowledge base"""
    result = await db.execute(
        select(VFSKnowledgeBase)
        .options(selectinload(VFSKnowledgeBase.files))
        .where(VFSKnowledgeBase.id == kb_id)
    )
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    if data.name is not None:
        kb.name = data.name
    if data.description is not None:
        kb.description = data.description
    if data.is_active is not None:
        kb.is_active = data.is_active

    await db.commit()
    await db.refresh(kb)

    return VFSKnowledgeBaseResponse(
        id=str(kb.id),
        name=kb.name,
        description=kb.description,
        file_count=kb.file_count,
        total_size_bytes=kb.total_size_bytes,
        is_active=kb.is_active,
        created_at=kb.created_at.isoformat() if kb.created_at else None,
        updated_at=kb.updated_at.isoformat() if kb.updated_at else None,
        files=[
            VFSFileResponse(
                id=str(f.id),
                filename=f.filename,
                title=f.title,
                size_bytes=f.size_bytes,
                summary=f.summary,
                created_at=f.created_at.isoformat() if f.created_at else None,
                updated_at=f.updated_at.isoformat() if f.updated_at else None,
            )
            for f in kb.files
        ]
    )


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_base(kb_id: UUID, db: AsyncSession = Depends(get_db)):
    """Delete a VFS knowledge base and all its files"""
    result = await db.execute(
        select(VFSKnowledgeBase).where(VFSKnowledgeBase.id == kb_id)
    )
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Delete directory from filesystem
    if os.path.exists(kb.vfs_path):
        shutil.rmtree(kb.vfs_path, ignore_errors=True)

    await db.delete(kb)
    await db.commit()


# ── File CRUD ────────────────────────────────────────────

@router.post("/{kb_id}/files", response_model=VFSFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    kb_id: UUID,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """Upload a .md file to a VFS knowledge base"""
    result = await db.execute(
        select(VFSKnowledgeBase).where(VFSKnowledgeBase.id == kb_id)
    )
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Validate file extension
    filename = file.filename or "untitled.md"
    if not filename.endswith(".md"):
        filename += ".md"

    # Save file
    file_path = os.path.join(kb.vfs_path, filename)
    content = await file.read()
    content_str = content.decode("utf-8")

    os.makedirs(kb.vfs_path, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content_str)

    size_bytes = len(content)

    # Auto-generate summary from first few lines
    summary = _generate_summary(content_str)

    # Create DB record
    vfs_file = VFSFile(
        knowledge_base_id=kb_id,
        filename=filename,
        title=title or _extract_title(content_str, filename),
        file_path=file_path,
        size_bytes=size_bytes,
        summary=summary,
    )
    db.add(vfs_file)

    # Update KB stats
    kb.file_count = (kb.file_count or 0) + 1
    kb.total_size_bytes = (kb.total_size_bytes or 0) + size_bytes

    await db.commit()
    await db.refresh(vfs_file)

    return VFSFileResponse(
        id=str(vfs_file.id),
        filename=vfs_file.filename,
        title=vfs_file.title,
        size_bytes=vfs_file.size_bytes,
        summary=vfs_file.summary,
        created_at=vfs_file.created_at.isoformat() if vfs_file.created_at else None,
        updated_at=vfs_file.updated_at.isoformat() if vfs_file.updated_at else None,
    )


@router.post("/{kb_id}/files/create", response_model=VFSFileResponse, status_code=status.HTTP_201_CREATED)
async def create_file_inline(
    kb_id: UUID,
    filename: str = Form(...),
    title: Optional[str] = Form(None),
    content: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """Create a .md file directly with content (inline editor)"""
    result = await db.execute(
        select(VFSKnowledgeBase).where(VFSKnowledgeBase.id == kb_id)
    )
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    if not filename.endswith(".md"):
        filename += ".md"

    file_path = os.path.join(kb.vfs_path, filename)
    os.makedirs(kb.vfs_path, exist_ok=True)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    size_bytes = len(content.encode("utf-8"))
    summary = _generate_summary(content)

    vfs_file = VFSFile(
        knowledge_base_id=kb_id,
        filename=filename,
        title=title or _extract_title(content, filename),
        file_path=file_path,
        size_bytes=size_bytes,
        summary=summary,
    )
    db.add(vfs_file)

    kb.file_count = (kb.file_count or 0) + 1
    kb.total_size_bytes = (kb.total_size_bytes or 0) + size_bytes

    await db.commit()
    await db.refresh(vfs_file)

    return VFSFileResponse(
        id=str(vfs_file.id),
        filename=vfs_file.filename,
        title=vfs_file.title,
        size_bytes=vfs_file.size_bytes,
        summary=vfs_file.summary,
        created_at=vfs_file.created_at.isoformat() if vfs_file.created_at else None,
        updated_at=vfs_file.updated_at.isoformat() if vfs_file.updated_at else None,
    )


@router.get("/{kb_id}/files", response_model=List[VFSFileResponse])
async def list_files(kb_id: UUID, db: AsyncSession = Depends(get_db)):
    """List all files in a VFS knowledge base"""
    result = await db.execute(
        select(VFSFile)
        .where(VFSFile.knowledge_base_id == kb_id)
        .order_by(VFSFile.created_at.desc())
    )
    files = result.scalars().all()

    return [
        VFSFileResponse(
            id=str(f.id),
            filename=f.filename,
            title=f.title,
            size_bytes=f.size_bytes,
            summary=f.summary,
            created_at=f.created_at.isoformat() if f.created_at else None,
            updated_at=f.updated_at.isoformat() if f.updated_at else None,
        )
        for f in files
    ]


@router.get("/{kb_id}/files/{file_id}")
async def get_file_content(kb_id: UUID, file_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get a file's content along with metadata"""
    result = await db.execute(
        select(VFSFile)
        .where(VFSFile.id == file_id, VFSFile.knowledge_base_id == kb_id)
    )
    vfs_file = result.scalar_one_or_none()
    if not vfs_file:
        raise HTTPException(status_code=404, detail="File not found")

    content = ""
    if os.path.exists(vfs_file.file_path):
        with open(vfs_file.file_path, "r", encoding="utf-8") as f:
            content = f.read()

    return {
        "id": str(vfs_file.id),
        "filename": vfs_file.filename,
        "title": vfs_file.title,
        "content": content,
        "size_bytes": vfs_file.size_bytes,
        "summary": vfs_file.summary,
        "created_at": vfs_file.created_at.isoformat() if vfs_file.created_at else None,
        "updated_at": vfs_file.updated_at.isoformat() if vfs_file.updated_at else None,
    }


@router.put("/{kb_id}/files/{file_id}", response_model=VFSFileResponse)
async def update_file(
    kb_id: UUID,
    file_id: UUID,
    data: VFSFileUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a file's title and/or content"""
    result = await db.execute(
        select(VFSFile)
        .where(VFSFile.id == file_id, VFSFile.knowledge_base_id == kb_id)
    )
    vfs_file = result.scalar_one_or_none()
    if not vfs_file:
        raise HTTPException(status_code=404, detail="File not found")

    # Get KB for stats update
    kb_result = await db.execute(
        select(VFSKnowledgeBase).where(VFSKnowledgeBase.id == kb_id)
    )
    kb = kb_result.scalar_one_or_none()

    if data.title is not None:
        vfs_file.title = data.title

    if data.content is not None:
        old_size = vfs_file.size_bytes or 0
        new_content = data.content
        with open(vfs_file.file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        new_size = len(new_content.encode("utf-8"))
        vfs_file.size_bytes = new_size
        vfs_file.summary = _generate_summary(new_content)

        if kb:
            kb.total_size_bytes = max(0, (kb.total_size_bytes or 0) - old_size + new_size)

    await db.commit()
    await db.refresh(vfs_file)

    return VFSFileResponse(
        id=str(vfs_file.id),
        filename=vfs_file.filename,
        title=vfs_file.title,
        size_bytes=vfs_file.size_bytes,
        summary=vfs_file.summary,
        created_at=vfs_file.created_at.isoformat() if vfs_file.created_at else None,
        updated_at=vfs_file.updated_at.isoformat() if vfs_file.updated_at else None,
    )


@router.delete("/{kb_id}/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(kb_id: UUID, file_id: UUID, db: AsyncSession = Depends(get_db)):
    """Delete a file from a VFS knowledge base"""
    result = await db.execute(
        select(VFSFile)
        .where(VFSFile.id == file_id, VFSFile.knowledge_base_id == kb_id)
    )
    vfs_file = result.scalar_one_or_none()
    if not vfs_file:
        raise HTTPException(status_code=404, detail="File not found")

    # Remove from filesystem
    if os.path.exists(vfs_file.file_path):
        os.remove(vfs_file.file_path)

    # Update KB stats
    kb_result = await db.execute(
        select(VFSKnowledgeBase).where(VFSKnowledgeBase.id == kb_id)
    )
    kb = kb_result.scalar_one_or_none()
    if kb:
        kb.file_count = max(0, (kb.file_count or 0) - 1)
        kb.total_size_bytes = max(0, (kb.total_size_bytes or 0) - (vfs_file.size_bytes or 0))

    await db.delete(vfs_file)
    await db.commit()


# ── Helper Functions ─────────────────────────────────────

def _extract_title(content: str, fallback: str = "Untitled") -> str:
    """Extract title from markdown content (first # heading)"""
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("# ") and not line.startswith("##"):
            return line[2:].strip()
    return fallback.replace(".md", "").replace("_", " ").replace("-", " ").title()


def _generate_summary(content: str, max_length: int = 300) -> str:
    """Generate a simple summary from the first paragraph of content"""
    lines = content.strip().split("\n")
    summary_parts = []
    for line in lines:
        line = line.strip()
        # Skip headings and empty lines
        if line.startswith("#") or not line:
            if summary_parts:
                break
            continue
        summary_parts.append(line)
        if len(" ".join(summary_parts)) > max_length:
            break
    
    summary = " ".join(summary_parts)
    if len(summary) > max_length:
        summary = summary[:max_length] + "..."
    return summary
