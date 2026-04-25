"""
Status API - Query result delivery status
"""
from fastapi import APIRouter, HTTPException
from typing import Optional

from app.redis_client import redis_client
from app.schemas.result import ResultStatusResponse, ResultListResponse


router = APIRouter()


@router.get("/{job_id}", response_model=ResultStatusResponse)
async def get_result_status(job_id: str):
    """
    Get status for a specific result job.
    """
    status_key = f"result:status:{job_id}"
    
    status = await redis_client.hget(status_key, "status")
    attempts_str = await redis_client.hget(status_key, "attempts")
    last_error = await redis_client.hget(status_key, "last_error")
    updated_at = await redis_client.hget(status_key, "updated_at")
    
    if not status:
        raise HTTPException(status_code=404, detail="Result status not found")
    
    return ResultStatusResponse(
        job_id=job_id,
        status=status,
        attempts=int(attempts_str or "0"),
        last_error=last_error if last_error else None,
        created_at=None,
        updated_at=None,
        sent_at=None
    )


@router.get("")
async def list_results(status: Optional[str] = None, limit: int = 20):
    """
    List recent results (from Redis using pattern).
    """
    client = await redis_client.connect()
    keys = []
    
    async for key in client.scan_iter(match="result:status:*", count=limit):
        keys.append(key)
    
    results = []
    for key in keys[:limit]:
        job_id = key.replace("result:status:", "")
        status_val = await redis_client.hget(key, "status")
        attempts_str = await redis_client.hget(key, "attempts")
        last_error = await redis_client.hget(key, "last_error")
        
        if status and status_val != status:
            continue
        
        results.append(ResultStatusResponse(
            job_id=job_id,
            status=status_val or "unknown",
            attempts=int(attempts_str or "0"),
            last_error=last_error if last_error else None,
            created_at=None,
            updated_at=None,
            sent_at=None
        ))
    
    return ResultListResponse(results=results, total=len(results))