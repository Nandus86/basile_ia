"""
Webhook Receive Endpoint — Normalizes, forwards, and queues on failure
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.pipeline import WebhookPipeline
from app.schemas.pipeline import WebhookReceivedResponse, TestWebhookRequest, TestWebhookResponse
from app.services.webhook_processor import normalize_webhook_payload, validate_pipeline_auth
from app.services.queue_publisher import enqueue_for_retry, save_job_status
from app.services.http_forwarder import forwarder


router = APIRouter()


@router.post("/{path}", response_model=WebhookReceivedResponse)
async def receive_webhook(
    path: str,
    request: Request,
    x_api_key: str = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db)
):
    """
    1. Normalize incoming payload via input_schema
    2. Try to forward to output_url (worker)
    3. If worker is down → store in Redis queue for background retry
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    # ── Find pipeline ──
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

    # ── Normalize ──
    try:
        normalized = normalize_webhook_payload(
            payload,
            pipeline.input_schema or {},
            path
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    job_id = normalized["job_id"]

    # ── Build worker-compatible payload ──
    worker_payload = {
        "message": normalized.get("message", ""),
        "session_id": normalized.get("session_id", ""),
    }
    for key in ("agent_id", "user_access_level", "context_data", "transition_data"):
        val = normalized.get(key)
        if val is not None:
            worker_payload[key] = val
            
    # Resolve callback
    callback_url = normalized.get("callback_url") or pipeline.default_callback_url
    egress_path = normalized.get("egress_pipeline_path") or pipeline.egress_pipeline_path
    
    if egress_path:
        worker_payload["pipeline_path"] = egress_path
        # If user provided an egress path but no explicit callback, point to the internal Egress service
        if not callback_url:
            # Assumes Egress runs on egress-api or accessible via gateway
            callback_url = f"http://basile-egress:8000/egress-api/result?pipeline_path={egress_path}"
            
    if callback_url:
        worker_payload["callback_url"] = callback_url

    # ── Try to forward immediately ──
    output_url = pipeline.output_url
    output_method = pipeline.output_method or "POST"

    success, response_data, error = await forwarder.forward(
        output_url, worker_payload, output_method
    )

    if success:
        await save_job_status(job_id, str(pipeline.id), "forwarded")
        return WebhookReceivedResponse(
            success=True,
            job_id=job_id,
            message="Webhook received and forwarded successfully"
        )

    # ── Worker is down — queue for retry ──
    await enqueue_for_retry(
        pipeline_id=str(pipeline.id),
        normalized=normalized,
        forward_url=output_url,
        forward_method=output_method,
    )
    await save_job_status(job_id, str(pipeline.id), "queued", last_error=error)

    return WebhookReceivedResponse(
        success=True,
        job_id=job_id,
        message=f"Worker unavailable — message queued for retry ({error})"
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
        message="Test successful — payload normalized correctly"
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