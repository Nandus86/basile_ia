"""
Queue Client - Interface for enqueuing tasks to the ARQ worker.
Used by the FastAPI application to send jobs to the background worker.
"""
from typing import Optional, Dict, Any
from arq import create_pool, ArqRedis
from arq.connections import RedisSettings
from app.worker.settings import get_redis_settings


# Global pool (initialized lazily)
_arq_pool: Optional[ArqRedis] = None


async def get_arq_pool() -> ArqRedis:
    """Get or create the ARQ Redis connection pool."""
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(
            get_redis_settings(),
            default_queue_name="basile:queue",
        )
    return _arq_pool


async def close_arq_pool():
    """Close the ARQ pool on shutdown."""
    global _arq_pool
    if _arq_pool is not None:
        await _arq_pool.close()
        _arq_pool = None


async def enqueue_process_message(
    message: str,
    session_id: str,
    agent_id: Optional[str] = None,
    user_access_level: str = "normal",
    context_data: Optional[Dict[str, Any]] = None,
    transition_data: Optional[Dict[str, Any]] = None,
    callback_url: Optional[str] = None,
) -> str:
    """
    Enqueue a message processing job.
    Returns the job ID for status tracking.
    """
    pool = await get_arq_pool()
    job = await pool.enqueue_job(
        "process_message_task",
        message=message,
        session_id=session_id,
        agent_id=agent_id,
        user_access_level=user_access_level,
        context_data=context_data,
        transition_data=transition_data,
        callback_url=callback_url,
    )
    return job.job_id


async def enqueue_process_structured(
    message: str,
    session_id: str,
    agent_id: Optional[str] = None,
    user_access_level: str = "normal",
    context_data: Optional[Dict[str, Any]] = None,
    transition_data: Optional[Dict[str, Any]] = None,
    callback_url: Optional[str] = None,
) -> str:
    """
    Enqueue a structured processing job.
    Returns the job ID for status tracking.
    """
    pool = await get_arq_pool()
    job = await pool.enqueue_job(
        "process_message_structured_task",
        message=message,
        session_id=session_id,
        agent_id=agent_id,
        user_access_level=user_access_level,
        context_data=context_data,
        transition_data=transition_data,
        callback_url=callback_url,
    )
    return job.job_id


async def get_job_status(job_id: str) -> Dict[str, Any]:
    """
    Get the status and result of a queued job.
    
    Returns:
        {
            "job_id": "...",
            "status": "queued" | "in_progress" | "completed" | "failed" | "not_found",
            "result": {...} | None
        }
    """
    import json
    from app.redis_client import redis_client
    
    # 1. Check if it's a RabbitMQ job stored in pure Redis
    try:
        job_data_str = await redis_client.client.get(f"job:{job_id}")
        if job_data_str:
            return json.loads(job_data_str)
    except Exception:
        pass
        
    from arq.jobs import Job, JobStatus
    
    pool = await get_arq_pool()
    job = Job(job_id, pool)
    
    status = await job.status()
    
    status_map = {
        JobStatus.deferred: "queued",
        JobStatus.queued: "queued",
        JobStatus.in_progress: "in_progress",
        JobStatus.complete: "completed",
        JobStatus.not_found: "not_found",
    }
    
    mapped_status = status_map.get(status, "unknown")
    
    result = None
    if mapped_status == "completed":
        try:
            result = await job.result()
        except Exception:
            result = None
    
    return {
        "job_id": job_id,
        "status": mapped_status,
        "result": result,
    }
