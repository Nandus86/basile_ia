"""
Queue Publisher - Publishes normalized webhooks to Redis queue
"""
import json
from typing import Dict, Any, Optional

from app.redis_client import redis_client


QUEUE_PREFIX = "pipeline:queue"


def get_queue_key(pipeline_id: str) -> str:
    """Get Redis queue key for pipeline"""
    return f"{QUEUE_PREFIX}:{pipeline_id}"


async def publish_to_queue(
    pipeline_id: str,
    job_data: Dict[str, Any],
    ttl: int = 86400
) -> str:
    """
    Publish normalized webhook data to Redis queue.
    Returns the job_id.
    """
    queue_key = get_queue_key(pipeline_id)
    job_id = job_data.get("job_id")
    
    queue_data = {
        "job_id": job_id,
        "pipeline_id": pipeline_id,
        "message": job_data.get("message"),
        "session_id": job_data.get("session_id"),
        "agent_id": job_data.get("agent_id"),
        "user_access_level": job_data.get("user_access_level", "normal"),
        "context_data": job_data.get("context_data"),
        "transition_data": job_data.get("transition_data"),
        "callback_url": job_data.get("callback_url"),
        "output_url": job_data.get("output_url"),
        "output_method": job_data.get("output_method", "POST"),
        "output_schema": job_data.get("output_schema"),
        "output_headers": job_data.get("output_headers"),
        "retry_config": job_data.get("retry_config"),
    }
    
    await redis_client.push_to_queue(
        queue_key,
        json.dumps(queue_data),
        ttl=ttl
    )
    
    return job_id


async def save_job_status(
    job_id: str,
    pipeline_id: str,
    status: str,
    attempts: int = 0,
    last_error: Optional[str] = None
) -> None:
    """Save job status to Redis for tracking"""
    status_key = f"pipeline:status:{job_id}"
    
    status_data = {
        "job_id": job_id,
        "pipeline_id": pipeline_id,
        "status": status,
        "attempts": attempts,
        "last_error": last_error,
    }
    
    await redis_client.set(
        status_key,
        json.dumps(status_data),
        expire=86400
    )


async def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Get job status from Redis"""
    status_key = f"pipeline:status:{job_id}"
    
    raw = await redis_client.get(status_key)
    if raw:
        return json.loads(raw)
    return None