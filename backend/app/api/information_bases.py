import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from uuid import UUID

from app.database import get_db
from app.models.information_base import InformationBase
from app.schemas.information_base import (
    InformationBaseCreate, InformationBaseUpdate, InformationBaseResponse, 
    InformationBaseList, InformationBaseSummary,
    InformationBaseWebhookRequest, InformationBaseWebhookResponse,
    InformationBaseWebhookDeleteRequest
)
from app.weaviate_client import get_weaviate, WeaviateClient

router = APIRouter()

@router.get("", response_model=InformationBaseList)
async def list_information_bases(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List all information bases"""
    result = await db.execute(select(InformationBase).offset(skip).limit(limit))
    bases = result.scalars().all()
    
    total_result = await db.execute(select(InformationBase))
    total = len(total_result.scalars().all())
    
    summaries = [
        InformationBaseSummary.model_validate(base)
        for base in bases
    ]
    return InformationBaseList(information_bases=summaries, total=total)

@router.get("/{base_id}", response_model=InformationBaseResponse)
async def get_information_base(
    base_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific information base"""
    result = await db.execute(select(InformationBase).where(InformationBase.id == base_id))
    base = result.scalar_one_or_none()
    
    if not base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Information Base not found")
        
    return base

@router.post("", response_model=InformationBaseResponse, status_code=status.HTTP_201_CREATED)
async def create_information_base(
    base_data: InformationBaseCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new Information Base"""
    # Check code uniqueness
    existing = await db.execute(select(InformationBase).where(InformationBase.code == base_data.code))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Information Base with this code already exists")
        
    base = InformationBase(**base_data.model_dump())
    db.add(base)
    await db.commit()
    await db.refresh(base)
    
    return base

@router.put("/{base_id}", response_model=InformationBaseResponse)
async def update_information_base(
    base_id: UUID,
    update_data: InformationBaseUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update an Information Base"""
    result = await db.execute(select(InformationBase).where(InformationBase.id == base_id))
    base = result.scalar_one_or_none()
    
    if not base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Information Base not found")
        
    # Check code uniqueness if changing code
    if update_data.code and update_data.code != base.code:
        existing = await db.execute(select(InformationBase).where(InformationBase.code == update_data.code))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Information Base with this code already exists")

    update_dict = update_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(base, key, value)
        
    await db.commit()
    await db.refresh(base)
    
    return base

@router.delete("/{base_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_information_base(
    base_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete an Information Base"""
    result = await db.execute(select(InformationBase).where(InformationBase.id == base_id))
    base = result.scalar_one_or_none()
    
    if not base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Information Base not found")
        
    await db.delete(base)
    await db.commit()

@router.post("/webhook", response_model=InformationBaseWebhookResponse)
async def webhook_ingest(
    request: InformationBaseWebhookRequest,
    db: AsyncSession = Depends(get_db),
    weaviate: WeaviateClient = Depends(get_weaviate)
):
    """
    Webhook to ingest data into an Information Base for a specific user ID.
    The payload should be structured according to the base's schemas.
    """
    # Verify the information base exists by code
    result = await db.execute(select(InformationBase).where(InformationBase.code == request.id_base))
    base = result.scalar_one_or_none()
    
    if not base:
        return InformationBaseWebhookResponse(
            success=False,
            message=f"Information Base with code {request.id_base} not found"
        )
        
    # In a real scenario, we might validate the request.data against base.content_schema and base.metadata_schema.
    # We will format the entire data as a structured text block for Weaviate to vectorize, and save raw generic metadata.
    
    content_str = json.dumps(request.data, ensure_ascii=False, indent=2)
    
    # Send to weaviate
    success = await weaviate.save_information_base_node(
        base_code=request.id_base,
        user_id=request.id,
        content=content_str,
        metadata=request.data,  # Using raw original data as generic metadata too
        external_id=request.external_id
    )
    
    if not success:
        return InformationBaseWebhookResponse(
            success=False,
            message="Failed to ingest data into vector database"
        )
        
    return InformationBaseWebhookResponse(
        success=True,
        message="Data ingested successfully"
    )

@router.post("/webhook/delete", response_model=InformationBaseWebhookResponse)
async def webhook_delete(
    request: InformationBaseWebhookDeleteRequest,
    db: AsyncSession = Depends(get_db),
    weaviate: WeaviateClient = Depends(get_weaviate)
):
    """
    Webhook to completely delete all vector nodes within an Information Base for a specific user ID.
    Useful for completely refreshing a user's data.
    """
    # Verify the information base exists by code
    result = await db.execute(select(InformationBase).where(InformationBase.code == request.id_base))
    base = result.scalar_one_or_none()
    
    if not base:
        return InformationBaseWebhookResponse(
            success=False,
            message=f"Information Base with code {request.id_base} not found"
        )
        
    # Delete from weaviate
    success = await weaviate.delete_information_base_nodes(
        base_code=request.id_base,
        user_id=request.id,
        external_id=request.external_id
    )
    
    if not success:
        return InformationBaseWebhookResponse(
            success=False,
            message="Failed to delete vectors from database"
        )
        
    return InformationBaseWebhookResponse(
        success=True,
        message="Vector data deleted successfully"
    )

