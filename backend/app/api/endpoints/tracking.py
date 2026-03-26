from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, desc
from typing import List, Optional
import json
import asyncio
import logging

from app.database import get_db
from app.models.job_log import JobLog
from app.schemas.job_log import JobLogSchema
from app.redis_client import redis_client

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/logs")
async def get_tracking_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    status: Optional[str] = None,
    path: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get paginated list of system webhook/job logs"""
    query = select(JobLog)
    
    if status:
        query = query.where(JobLog.status == status)
    if path:
        query = query.where(JobLog.webhook_path.ilike(f"%{path}%"))
        
    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Get items
    query = query.order_by(desc(JobLog.created_at)).offset(skip).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()
    
    return {
        "items": [JobLogSchema.model_validate(log) for log in logs],
        "total": total,
        "skip": skip,
        "limit": limit
    }

@router.get("/stats")
async def get_tracking_stats(db: AsyncSession = Depends(get_db)):
    """Get aggregated stats for dashboard charts"""
    # Group by status
    status_query = select(JobLog.status, func.count(JobLog.id)).group_by(JobLog.status)
    status_result = await db.execute(status_query)
    status_counts = [{"status": row[0], "count": row[1]} for row in status_result.all()]
    
    # Group by path (top 5)
    path_query = select(JobLog.webhook_path, func.count(JobLog.id)).group_by(JobLog.webhook_path).order_by(desc(func.count(JobLog.id))).limit(5)
    path_result = await db.execute(path_query)
    path_counts = [{"path": row[0], "count": row[1]} for row in path_result.all()]
    
    # Timeline (last 7 days grouped by day) -> simple implementation counting entries
    # In PostgreSQL we could use date_trunc. For SQLite/generic, we simplify:
    
    return {
        "by_status": status_counts,
        "by_path": path_counts,
        "total_calls": sum(s["count"] for s in status_counts)
    }

@router.post("/jobs/{job_id}/test")
async def test_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """
    Re-test an existing job synchronously using its original payload,
    without triggering the final output webhook (callback_url).
    """
    query = select(JobLog).where(JobLog.job_id == job_id)
    result = await db.execute(query)
    job_log = result.scalar_one_or_none()
    
    if not job_log:
        raise HTTPException(status_code=404, detail="Job not found")
        
    payload = job_log.request_data
    if not payload:
        raise HTTPException(status_code=400, detail="Job has no request payload")
        
    from app.worker.tasks import process_message_task
    import time
    
    start_time = time.time()
    
    try:
        import json
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
                
        # Extrair os campos com defaults básicos
        message = payload.get("message", "Teste vazio")
        session_id = payload.get("session_id", "test_session_id")
        agent_id = payload.get("agent_id")
        user_access_level = payload.get("user_access_level", "normal")
        
        # Garante que context_data seja um dict válido (converte null/None para {})
        context_data = payload.get("context_data")
        if context_data is None or not isinstance(context_data, dict):
            context_data = {}
            
        # Mapeamento do request body extra, caso seja payload puro sem 'context_data'
        standard_keys = {"message", "session_id", "agent_id", "user_access_level", "metadata", "context_data", "transition_data", "callback_url"}
        for k, v in payload.items():
            if k not in standard_keys:
                context_data[k] = v
                
        # Força callback_url = None para não disparar webhook de saída
        result_data = await process_message_task(
            ctx={},
            message=message,
            session_id=session_id,
            agent_id=agent_id,
            user_access_level=user_access_level,
            context_data=context_data,
            transition_data=payload.get("transition_data"),
            callback_url=None  # AQUI EVITAMOS O DISPARO DE SAÍDA
        )
        
        processing_time = (time.time() - start_time) * 1000
        
        return {
            "success": True,
            "job_id": job_id,
            "processing_time_ms": int(processing_time),
            "test_response": result_data
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to test job: {str(e)}")

@router.post("/jobs/{job_id}/abort")
async def abort_job(job_id: str):
    """Abort an ongoing job currently running in the worker"""
    try:
        # Publish abort signal for worker to intercept
        await redis_client.publish("job_control", f"abort:{job_id}")
        return {"success": True, "message": f"Sinal de abort enviado para o job {job_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to abort job: {str(e)}")


@router.post("/jobs/{job_id}/resend")
async def resend_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """Resend the job's response_data to its callback_url"""
    query = select(JobLog).where(JobLog.job_id == job_id)
    result = await db.execute(query)
    job_log = result.scalar_one_or_none()
    
    if not job_log:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if not job_log.callback_url:
        raise HTTPException(status_code=400, detail="Job has no callback_url to resend to")
    
    if not job_log.response_data:
        raise HTTPException(status_code=400, detail="Job has no response_data to resend")
    
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            await client.post(job_log.callback_url, json=job_log.response_data, timeout=10.0)
        return {"success": True, "message": f"Response reenviado para {job_log.callback_url}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resend callback: {str(e)}")


@router.post("/jobs/{job_id}/human-response")
async def human_response_job(
    job_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db)
):
    """Send a human-written response replacing the output field, sending to callback_url"""
    human_text = body.get("human_text")
    if not human_text:
        raise HTTPException(status_code=400, detail="human_text is required")
    
    query = select(JobLog).where(JobLog.job_id == job_id)
    result = await db.execute(query)
    job_log = result.scalar_one_or_none()
    
    if not job_log:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if not job_log.callback_url:
        raise HTTPException(status_code=400, detail="Job has no callback_url to send to")
    
    if not job_log.response_data:
        raise HTTPException(status_code=400, detail="Job has no response_data to modify")
    
    # Replicate full response_data and replace result (que agora é string)
    import copy
    modified_response = copy.deepcopy(job_log.response_data)
    
    # Estrutura: { status, job_id, result: "string", agent_used, transition_data }
    modified_response["result"] = human_text
    
    # Update job_log.response_data in DB
    job_log.response_data = modified_response
    await db.commit()
    
    # Send to callback_url
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            await client.post(job_log.callback_url, json=modified_response, timeout=10.0)
        return {"success": True, "message": f"Human response enviada para {job_log.callback_url}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send human response: {str(e)}")


# ─────────────────────────────────────────────────
# SSE (Server-Sent Events) - Real-time job updates
# ─────────────────────────────────────────────────

@router.get("/stream")
async def stream_job_updates(request: Request):
    """SSE endpoint that streams real-time job status updates via Redis PubSub"""
    async def event_generator():
        client = await redis_client.connect()
        pubsub = client.pubsub()
        await pubsub.subscribe("job_updates")
        logger.info("SSE client connected on /tracking/stream")
        try:
            async for message in pubsub.listen():
                if await request.is_disconnected():
                    logger.info("SSE client disconnected from /tracking/stream")
                    break
                if message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode()
                    yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"SSE stream error: {e}")
        finally:
            try:
                await pubsub.unsubscribe("job_updates")
                await pubsub.close()
            except Exception:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
