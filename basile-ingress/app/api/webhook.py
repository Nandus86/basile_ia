"""
Webhook Receive Endpoint - Receives and processes incoming webhooks
"""
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.pipeline import WebhookPipeline
from app.schemas.pipeline import WebhookReceivedResponse, TestWebhookRequest, TestWebhookResponse
from app.services.webhook_processor import normalize_webhook_payload, validate_pipeline_auth
from app.services.queue_publisher import publish_to_queue, save_job_status


router = APIRouter()


@router.post("/{path}", response_model=WebhookReceivedResponse)
async def receive_webhook(
    path: str,
    request: Request,
    x_api_key: str = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db)
):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    
    query = select(WebhookPipeline).where(
        WebhookPipeline.path == path,
        WebhookPipeline.is_active == True
    )
    result = await db.execute(query)
    pipeline = result.scalar_one_or_none()
    
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found or inactive")
    
    if not validate_pipeline_auth(pipeline.auth_type, pipeline.auth_token, x_api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    
    try:
        normalized = normalize_webhook_payload(
            payload,
            pipeline.input_schema or {},
            path
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    normalized["output_url"] = pipeline.output_url
    normalized["output_method"] = pipeline.output_method
    normalized["output_schema"] = pipeline.output_schema
    normalized["output_headers"] = pipeline.output_headers
    normalized["retry_config"] = pipeline.retry_config
    
    job_id = await publish_to_queue(str(pipeline.id), normalized)
    
    await save_job_status(job_id, str(pipeline.id), "queued")
    
    return WebhookReceivedResponse(
        success=True,
        job_id=job_id,
        message="Webhook received and queued for processing"
    )


@router.post("/test/{path}", response_model=TestWebhookResponse)
async def test_webhook(
    path: str,
    test_request: TestWebhookRequest,
    db: AsyncSession = Depends(get_db)
):
    query = select(WebhookPipeline).where(
        WebhookPipeline.path == path,
        WebhookPipeline.is_active == True
    )
    result = await db.execute(query)
    pipeline = result.scalar_one_or_none()
    
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found or inactive")
    
    try:
        normalized = normalize_webhook_payload(
            test_request.payload,
            pipeline.input_schema or {},
            path
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return TestWebhookResponse(
        success=True,
        pipeline=path,
        normalized=normalized,
        message="Test successful - payload normalized correctly"
    )


@router.get("/{path}")
async def get_pipeline_info(
    path: str,
    db: AsyncSession = Depends(get_db)
):
    query = select(WebhookPipeline).where(WebhookPipeline.path == path)
    result = await db.execute(query)
    pipeline = result.scalar_one_or_none()
    
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    
    return {
        "id": str(pipeline.id),
        "name": pipeline.name,
        "path": pipeline.path,
        "is_active": pipeline.is_active,
        "auth_type": pipeline.auth_type,
        "input_schema": pipeline.input_schema,
        "output_url": pipeline.output_url,
    }