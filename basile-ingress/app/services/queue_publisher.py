"""
Queue Publisher - Stores failed-to-forward jobs in Redis for background retry
"""
import json
from typing import Dict, Any, Optional

from app.redis_client import redis_client


QUEUE_PREFIX = "pipeline:queue"
STATUS_PREFIX = "pipeline:status"


def get_queue_key(pipeline_id: str) -> str:
    return f"{QUEUE_PREFIX}:{pipeline_id}"


async def enqueue_for_retry(
    pipeline_id: str,
    normalized: Dict[str, Any],
    forward_url: str,
    forward_method: str = "POST",
    ttl: int = 86400,
) -> str:
    """
    Store a normalized job in Redis queue so the background dispatcher
    can retry forwarding to the worker later.
    """
    queue_key = get_queue_key(pipeline_id)
    job_id = normalized.get("job_id")

    # Start with all fields from normalized to support dynamic custom payloads
    queue_data = {k: v for k, v in normalized.items() if not k.startswith("_")}
    # Overlay metadata and specific fields
    queue_data.update({
        "pipeline_id": pipeline_id,
        "_forward_url": forward_url,
        "_forward_method": forward_method,
        "_retry_count": 0,
    })

    await redis_client.push_to_queue(
        queue_key,
        json.dumps(queue_data, default=str),
        ttl=ttl,
    )
    return job_id


async def save_job_status(
    job_id: str,
    pipeline_id: str,
    status: str,
    attempts: int = 0,
    last_error: Optional[str] = None,
) -> None:
    """Save job status to Redis for tracking"""
    from datetime import datetime, timezone

    await redis_client.set(
        f"{STATUS_PREFIX}:{job_id}",
        json.dumps({
            "job_id": job_id,
            "pipeline_id": pipeline_id,
            "status": status,
            "attempts": attempts,
            "last_error": last_error,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }),
        expire=86400,
    )


async def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    raw = await redis_client.get(f"{STATUS_PREFIX}:{job_id}")
    if raw:
        return json.loads(raw)
    return None