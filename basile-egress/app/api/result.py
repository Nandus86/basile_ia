"""
Result API - Receives results from worker and sends to webhooks
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone

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
    status_data = {
        "job_id": job_id,
        "status": status,
        "attempts": str(attempts),
        "last_error": last_error or "",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    
    import json
    await redis_client.hset(status_key, "status", status)
    await redis_client.hset(status_key, "attempts", str(attempts))
    await redis_client.hset(status_key, "last_error", last_error or "")
    await redis_client.hset(status_key, "updated_at", datetime.now(timezone.utc).isoformat())


@router.post("", response_model=ResultOutput)
async def receive_result(result: ResultInput):
    """
    Receive result from worker and send to webhook.
    
    Pipeline:
    1. Transform output using output_schema
    2. Send to output_url with retry
    3. Save status to Redis
    """
    await save_result_status(result.job_id, "processing", attempts=0)
    
    transformed = transform_output(
        result.response,
        result.output_schema,
        result.job_id,
        result.session_id,
        result.agent_used
    )
    
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
async def receive_result_sync(result: ResultInput):
    """
    Receive result and send to webhook synchronously without retry.
    """
    transformed = transform_output(
        result.response,
        result.output_schema,
        result.job_id,
        result.session_id,
        result.agent_used
    )
    
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