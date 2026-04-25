"""
Pipeline CRUD Endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from uuid import UUID

from app.database import get_db
from app.models.pipeline import WebhookPipeline
from app.schemas.pipeline import (
    WebhookPipelineCreate,
    WebhookPipelineUpdate,
    WebhookPipelineResponse,
    WebhookPipelineList,
)


router = APIRouter()


@router.get("", response_model=WebhookPipelineList)
async def list_pipelines(skip: int = 0, limit: int = 20, db: AsyncSession = Depends(get_db)):
    query = select(WebhookPipeline).offset(skip).limit(limit)
    result = await db.execute(query)
    pipelines = result.scalars().all()
    
    count_query = select(WebhookPipeline.id)
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())
    
    return WebhookPipelineList(
        pipelines=[
            WebhookPipelineResponse(
                id=p.id,
                name=p.name,
                path=p.path,
                is_active=p.is_active,
                description=p.description,
                input_schema=p.input_schema or {},
                auth_type=p.auth_type,
                output_url=p.output_url,
                output_method=p.output_method,
                output_schema=p.output_schema,
                output_headers=p.output_headers,
                retry_config=p.retry_config,
                created_at=p.created_at,
                updated_at=p.updated_at,
                has_auth_token=bool(p.auth_token),
            )
            for p in pipelines
        ],
        total=total
    )


@router.post("", response_model=WebhookPipelineResponse)
async def create_pipeline(
    pipeline: WebhookPipelineCreate,
    db: AsyncSession = Depends(get_db)
):
    query = select(WebhookPipeline).where(WebhookPipeline.path == pipeline.path)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Pipeline with this path already exists")
    
    if pipeline.auth_type != "none" and not pipeline.auth_token:
        raise HTTPException(status_code=400, detail="auth_token is required when auth_type is not 'none'")
    
    db_pipeline = WebhookPipeline(
        name=pipeline.name,
        path=pipeline.path,
        is_active=pipeline.is_active,
        description=pipeline.description,
        input_schema=pipeline.input_schema.model_dump() if hasattr(pipeline.input_schema, 'model_dump') else pipeline.input_schema,
        auth_type=pipeline.auth_type,
        auth_token=pipeline.auth_token,
        output_url=pipeline.output_url,
        output_method=pipeline.output_method,
        output_schema=pipeline.output_schema,
        output_headers=pipeline.output_headers,
        retry_config=pipeline.retry_config,
    )
    db.add(db_pipeline)
    await db.commit()
    await db.refresh(db_pipeline)
    
    return WebhookPipelineResponse(
        id=db_pipeline.id,
        name=db_pipeline.name,
        path=db_pipeline.path,
        is_active=db_pipeline.is_active,
        description=db_pipeline.description,
        input_schema=db_pipeline.input_schema or {},
        auth_type=db_pipeline.auth_type,
        output_url=db_pipeline.output_url,
        output_method=db_pipeline.output_method,
        output_schema=db_pipeline.output_schema,
        output_headers=db_pipeline.output_headers,
        retry_config=db_pipeline.retry_config,
        created_at=db_pipeline.created_at,
        updated_at=db_pipeline.updated_at,
        has_auth_token=bool(db_pipeline.auth_token),
    )


@router.get("/{pipeline_id}", response_model=WebhookPipelineResponse)
async def get_pipeline(pipeline_id: UUID, db: AsyncSession = Depends(get_db)):
    query = select(WebhookPipeline).where(WebhookPipeline.id == pipeline_id)
    result = await db.execute(query)
    pipeline = result.scalar_one_or_none()
    
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    
    return WebhookPipelineResponse(
        id=pipeline.id,
        name=pipeline.name,
        path=pipeline.path,
        is_active=pipeline.is_active,
        description=pipeline.description,
        input_schema=pipeline.input_schema or {},
        auth_type=pipeline.auth_type,
        output_url=pipeline.output_url,
        output_method=pipeline.output_method,
        output_schema=pipeline.output_schema,
        output_headers=pipeline.output_headers,
        retry_config=pipeline.retry_config,
        created_at=pipeline.created_at,
        updated_at=pipeline.updated_at,
        has_auth_token=bool(pipeline.auth_token),
    )


@router.put("/{pipeline_id}", response_model=WebhookPipelineResponse)
async def update_pipeline(
    pipeline_id: UUID,
    pipeline_update: WebhookPipelineUpdate,
    db: AsyncSession = Depends(get_db)
):
    query = select(WebhookPipeline).where(WebhookPipeline.id == pipeline_id)
    result = await db.execute(query)
    db_pipeline = result.scalar_one_or_none()
    
    if not db_pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    
    update_data = pipeline_update.model_dump(exclude_unset=True)
    
    for key, value in update_data.items():
        if key == "input_schema" and value:
            value = value.model_dump() if hasattr(value, 'model_dump') else value
        setattr(db_pipeline, key, value)
    
    await db.commit()
    await db.refresh(db_pipeline)
    
    return WebhookPipelineResponse(
        id=db_pipeline.id,
        name=db_pipeline.name,
        path=db_pipeline.path,
        is_active=db_pipeline.is_active,
        description=db_pipeline.description,
        input_schema=db_pipeline.input_schema or {},
        auth_type=db_pipeline.auth_type,
        output_url=db_pipeline.output_url,
        output_method=db_pipeline.output_method,
        output_schema=db_pipeline.output_schema,
        output_headers=db_pipeline.output_headers,
        retry_config=db_pipeline.retry_config,
        created_at=db_pipeline.created_at,
        updated_at=db_pipeline.updated_at,
        has_auth_token=bool(db_pipeline.auth_token),
    )


@router.delete("/{pipeline_id}")
async def delete_pipeline(pipeline_id: UUID, db: AsyncSession = Depends(get_db)):
    query = select(WebhookPipeline).where(WebhookPipeline.id == pipeline_id)
    result = await db.execute(query)
    pipeline = result.scalar_one_or_none()
    
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    
    await db.delete(pipeline)
    await db.commit()
    return {"message": "Pipeline deleted successfully"}