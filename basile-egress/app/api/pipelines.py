"""
Egress Pipelines CRUD API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from uuid import UUID

from app.database import get_db
from app.models.pipeline import EgressPipeline
from app.schemas.pipeline import (
    EgressPipelineCreate,
    EgressPipelineUpdate,
    EgressPipelineResponse,
    EgressPipelineListResponse
)


router = APIRouter()


@router.get("", response_model=EgressPipelineListResponse)
async def list_pipelines(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    query = select(EgressPipeline).order_by(EgressPipeline.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    pipelines = result.scalars().all()
    
    count_query = select(EgressPipeline)
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())
    
    return {"pipelines": pipelines, "total": total}


@router.post("", response_model=EgressPipelineResponse)
async def create_pipeline(pipeline: EgressPipelineCreate, db: AsyncSession = Depends(get_db)):
    # Check if path already exists
    query = select(EgressPipeline).where(EgressPipeline.path == pipeline.path)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Pipeline path already exists")
    
    db_pipeline = EgressPipeline(**pipeline.model_dump())
    db.add(db_pipeline)
    await db.commit()
    await db.refresh(db_pipeline)
    return db_pipeline


@router.get("/{pipeline_id}", response_model=EgressPipelineResponse)
async def get_pipeline(pipeline_id: UUID, db: AsyncSession = Depends(get_db)):
    query = select(EgressPipeline).where(EgressPipeline.id == pipeline_id)
    result = await db.execute(query)
    pipeline = result.scalar_one_or_none()
    
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    
    return pipeline


@router.put("/{pipeline_id}", response_model=EgressPipelineResponse)
async def update_pipeline(
    pipeline_id: UUID,
    pipeline_update: EgressPipelineUpdate,
    db: AsyncSession = Depends(get_db)
):
    query = select(EgressPipeline).where(EgressPipeline.id == pipeline_id)
    result = await db.execute(query)
    db_pipeline = result.scalar_one_or_none()
    
    if not db_pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    
    if pipeline_update.path and pipeline_update.path != db_pipeline.path:
        path_query = select(EgressPipeline).where(EgressPipeline.path == pipeline_update.path)
        path_result = await db.execute(path_query)
        if path_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Pipeline path already exists")
    
    update_data = pipeline_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_pipeline, key, value)
        
    await db.commit()
    await db.refresh(db_pipeline)
    return db_pipeline


@router.delete("/{pipeline_id}")
async def delete_pipeline(pipeline_id: UUID, db: AsyncSession = Depends(get_db)):
    query = select(EgressPipeline).where(EgressPipeline.id == pipeline_id)
    result = await db.execute(query)
    db_pipeline = result.scalar_one_or_none()
    
    if not db_pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
        
    await db.delete(db_pipeline)
    await db.commit()
    return {"message": "Pipeline deleted successfully"}
