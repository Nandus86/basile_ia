"""
Result API - Receives results from worker and sends to webhooks
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timezone

from app.database import get_db
from app.models.pipeline import EgressPipeline
from app.schemas.result import ResultInput, ResultOutput
from app.services.output_transformer import transform_output
from app.services.webhook_sender import webhook_sender
from app.redis_client import redis_client


router = APIRouter()


async def save_result_status(
    job_id: str,
    status: str,
    attempts: int = 0,
    last_error: str = None
) -> None:
    """Save result status to Redis"""
    status_key = f"result:status:{job_id}"
    
    import json
    await redis_client.hset(status_key, "status", status)
    await redis_client.hset(status_key, "attempts", str(attempts))
    await redis_client.hset(status_key, "last_error", last_error or "")
    await redis_client.hset(status_key, "updated_at", datetime.now(timezone.utc).isoformat())


async def _resolve_pipeline(result: ResultInput, db: AsyncSession):
    """Resolve configuration from EgressPipeline if pipeline_path is provided"""
    if not result.pipeline_path:
        if not result.output_url:
            raise HTTPException(status_code=400, detail="Either output_url or pipeline_path must be provided")
        return result

    query = select(EgressPipeline).where(
        EgressPipeline.path == result.pipeline_path,
        EgressPipeline.is_active == True
    )
    db_result = await db.execute(query)
    pipeline = db_result.scalar_one_or_none()

    if not pipeline:
        raise HTTPException(status_code=404, detail=f"Active pipeline '{result.pipeline_path}' not found")

    # Override result input with pipeline config
    result.output_url = pipeline.output_url
    result.output_method = pipeline.output_method
    
    if pipeline.output_schema:
        result.output_schema = pipeline.output_schema
    if pipeline.output_headers:
        result.output_headers = pipeline.output_headers
    if pipeline.retry_config:
        result.retry_config = pipeline.retry_config
        
    return result


@router.post("", response_model=ResultOutput)
async def receive_result(result: ResultInput, db: AsyncSession = Depends(get_db)):
    """
    Receive result from worker and send to webhook.
    """
    result = await _resolve_pipeline(result, db)
    
    await save_result_status(result.job_id, "processing", attempts=0)
    
    try:
        transformed = transform_output(
            result.response,
            result.output_schema,
            result.job_id,
            result.session_id,
            result.agent_used
        )
    except ValueError as ve:
        await save_result_status(result.job_id, "failed", attempts=0, last_error=str(ve))
        raise HTTPException(status_code=422, detail=str(ve))
    
    retry_config = result.retry_config or {
        "maxRetries": 3,
        "delays": [1000, 5000, 15000]
    }
    
    success, error_msg, attempts = await webhook_sender.send_with_retry(
        result.output_url,
        transformed,
        result.output_method,
        result.output_headers,
        retry_config
    )
    
    if success:
        await save_result_status(result.job_id, "sent", attempts, None)
        return ResultOutput(
            success=True,
            job_id=result.job_id,
            message="Result sent successfully",
            attempts=attempts,
            status="sent"
        )
    else:
        await save_result_status(result.job_id, "failed", attempts, error_msg)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to send result after {attempts} attempts: {error_msg}"
        )


@router.post("/sync", response_model=ResultOutput)
async def receive_result_sync(result: ResultInput, db: AsyncSession = Depends(get_db)):
    """
    Receive result and send to webhook synchronously without retry.
    """
    result = await _resolve_pipeline(result, db)
    
    try:
        transformed = transform_output(
            result.response,
            result.output_schema,
            result.job_id,
            result.session_id,
            result.agent_used
        )
    except ValueError as ve:
        await save_result_status(result.job_id, "failed", attempts=0, last_error=str(ve))
        raise HTTPException(status_code=422, detail=str(ve))
    
    success, error_msg = await webhook_sender.send(
        result.output_url,
        transformed,
        result.output_method,
        result.output_headers
    )
    
    if success:
        await save_result_status(result.job_id, "sent", 1, None)
        return ResultOutput(
            success=True,
            job_id=result.job_id,
            message="Result sent successfully",
            attempts=1,
            status="sent"
        )
    else:
        await save_result_status(result.job_id, "failed", 1, error_msg)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to send result: {error_msg}"
        )