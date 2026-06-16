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


@router.delete("/antibot/{session_id}")
async def reset_antibot_block(session_id: str):
    """Reset anti-bot block for a specific session"""
    await redis_client.reset_antibot(session_id)
    logger.info(f"[AntiBot] 🔓 Session {session_id} unblocked by user")
    return {"success": True, "message": f"Bloqueio Anti-Bot removido para sessão {session_id}"}


@router.post("/antibot/{session_id}")
async def block_antibot_session(session_id: str, ttl: int = 86400):
    """Manually flag a session as a bot and block it. Default 24h (86400s) TTL."""
    await redis_client.set_antibot_blocked(session_id, ttl)
    logger.info(f"[AntiBot] 🔒 Session {session_id} manually BLOCKED as bot by user")
    return {"success": True, "message": f"Sessão {session_id} bloqueada como BOT."}


@router.post("/sessions/{session_id}/unlock")
async def unlock_session(session_id: str):
    """Release the concurrency lock and clear the message buffer for a session"""
    lock_owner = await redis_client.get_user_lock_owner(session_id)
    await redis_client.release_user_lock(session_id)
    await redis_client.drain_buffer(session_id)
    logger.info(f"[Guard] 🔓 Session {session_id} manually unlocked by user. Lock owner was {lock_owner}")
    return {
        "success": True, 
        "message": f"Trava de concorrência e buffer limpos para a sessão {session_id}.",
        "previous_owner": lock_owner
    }


@router.get("/logs")
async def get_tracking_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    status: Optional[str] = None,
    path: Optional[str] = None,
    session_id: Optional[str] = None,
    church_name: Optional[str] = None,
    member_name: Optional[str] = None,
    user_message: Optional[str] = None,
    agent_response: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get paginated list of system webhook/job logs (lightweight list view).
    Uses denormalized indexed columns for fast filtering instead of JSON casting."""
    query = select(JobLog)

    if status:
        query = query.where(JobLog.status == status)
    if path:
        from sqlalchemy import or_
        paths = [p.strip() for p in path.split(",") if p.strip()]
        if paths:
            conditions = [JobLog.webhook_path.ilike(f"%{p}%") for p in paths]
            query = query.where(or_(*conditions))
    if session_id:
        query = query.where(JobLog.session_id.ilike(f"%{session_id}%"))
    if church_name:
        query = query.where(JobLog.church_name.ilike(f"%{church_name}%"))
    if member_name:
        query = query.where(JobLog.member_name.ilike(f"%{member_name}%"))
    if user_message:
        query = query.where(JobLog.user_message.ilike(f"%{user_message}%"))
    if agent_response:
        query = query.where(JobLog.agent_response.ilike(f"%{agent_response}%"))

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(desc(JobLog.created_at)).offset(skip).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()

    items = []
    for log in logs:
        item = JobLogSchema.model_validate(log)
        # Use denormalized columns directly (already populated at write time)
        if not item.session_id:
            item.session_id = log.session_id
        if not item.church_name:
            item.church_name = log.church_name
        if not item.member_fullname:
            item.member_fullname = log.member_name
        if not item.user_message:
            item.user_message = log.user_message
        if not item.agent_response:
            item.agent_response = log.agent_response

        # Fallback: extract from JSON only if denormalized columns are empty
        if not item.church_name or not item.member_fullname or not item.user_message:
            request_data = log.request_data
            if isinstance(request_data, dict):
                if not item.session_id:
                    item.session_id = request_data.get("session_id")
                if not item.church_name:
                    church = request_data.get("church") or {}
                    item.church_name = church.get("church_name")
                if not item.member_fullname:
                    member = request_data.get("member") or {}
                    context_data = request_data.get("context_data") or {}
                    item.member_fullname = member.get("fullname") or context_data.get("name") or request_data.get("name")
                if not item.user_message:
                    item.user_message = request_data.get("message")

        if not item.agent_response:
            response_data = log.response_data
            if isinstance(response_data, dict):
                item.agent_response = response_data.get("result") or response_data.get("response") or response_data.get("output") or response_data.get("resposta")
                if isinstance(item.agent_response, dict):
                    item.agent_response = item.agent_response.get("result") or item.agent_response.get("output") or item.agent_response.get("response") or str(item.agent_response)

        # Keep list payload small for stable pagination with high limits.
        item.request_data = None
        item.response_data = None

        items.append(item)

    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit
    }



@router.get("/jobs/{job_id}")
async def get_job_details(job_id: str, db: AsyncSession = Depends(get_db)):
    """Get complete job payload/details for modal inspection."""
    query = select(JobLog).where(JobLog.job_id == job_id)
    result = await db.execute(query)
    job_log = result.scalar_one_or_none()

    if not job_log:
        raise HTTPException(status_code=404, detail="Job not found")

    item = JobLogSchema.model_validate(job_log)
    request_data = job_log.request_data
    if isinstance(request_data, str):
        try:
            request_data = json.loads(request_data)
        except json.JSONDecodeError:
            request_data = None

    if isinstance(request_data, dict):
        if not item.session_id:
            item.session_id = request_data.get("session_id")
        church = request_data.get("church") or {}
        member = request_data.get("member") or {}
        context_data = request_data.get("context_data") or {}
        item.church_name = church.get("church_name")
        item.member_fullname = member.get("fullname") or context_data.get("name") or request_data.get("name")
        item.user_message = request_data.get("message")
        
    response_data = job_log.response_data
    if isinstance(response_data, str):
        try:
            response_data = json.loads(response_data)
        except json.JSONDecodeError:
            response_data = None
            
    if isinstance(response_data, dict):
        item.agent_response = response_data.get("result") or response_data.get("response") or response_data.get("output") or response_data.get("resposta")
        if isinstance(item.agent_response, dict):
            item.agent_response = item.agent_response.get("result") or item.agent_response.get("output") or item.agent_response.get("response") or str(item.agent_response)

    return item

@router.get("/stats")
async def get_tracking_stats(db: AsyncSession = Depends(get_db)):
    """Get aggregated stats for dashboard charts"""
    # Group by status
    status_query = select(JobLog.status, func.count(JobLog.id)).group_by(JobLog.status)
    status_result = await db.execute(status_query)
    status_counts = [{"status": row[0], "count": row[1]} for row in status_result.all()]
    
    # Group by path (all paths)
    path_query = select(JobLog.webhook_path, func.count(JobLog.id)).group_by(JobLog.webhook_path).order_by(desc(func.count(JobLog.id)))
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

@router.post("/jobs/{job_id}/redo")
async def redo_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """
    Redo an existing job: takes the original request_data (input payload)
    and reprocesses it as a brand-new job through the full pipeline.
    Creates a new JobLog entry with the new result.
    The callback_url is preserved so the new result can be resent.
    """
    query = select(JobLog).where(JobLog.job_id == job_id)
    result = await db.execute(query)
    job_log = result.scalar_one_or_none()

    if not job_log:
        raise HTTPException(status_code=404, detail="Job not found")

    payload = job_log.request_data
    if not payload:
        raise HTTPException(status_code=400, detail="Job has no request payload to redo")

    from app.worker.tasks import process_message_task
    import time
    import uuid as uuid_mod

    start_time = time.time()

    try:
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}

        # Extract fields from original payload
        message = payload.get("message", "Teste vazio")
        session_id = payload.get("session_id", "redo_session_id")
        agent_id = payload.get("agent_id")
        user_access_level = payload.get("user_access_level", "normal")

        context_data = payload.get("context_data")
        if context_data is None or not isinstance(context_data, dict):
            context_data = {}

        standard_keys = {"message", "session_id", "agent_id", "user_access_level", "metadata", "context_data", "transition_data", "callback_url"}
        for k, v in payload.items():
            if k not in standard_keys:
                context_data[k] = v

        # Generate new job ID
        new_job_id = str(uuid_mod.uuid4())

        # Create new JobLog entry (queued)
        new_job_log = JobLog(
            job_id=new_job_id,
            webhook_path=job_log.webhook_path,
            request_data=payload,
            callback_url=job_log.callback_url,
            status="in_progress",
        )
        db.add(new_job_log)
        await db.commit()
        await db.refresh(new_job_log)

        # Execute the full pipeline WITH callback_url (so it can be resent)
        # But we pass callback_url=None here to avoid auto-sending — user decides
        result_data = await process_message_task(
            ctx={},
            message=message,
            session_id=session_id,
            agent_id=agent_id,
            user_access_level=user_access_level,
            context_data=context_data,
            transition_data=payload.get("transition_data"),
            callback_url=None  # Don't auto-send; user can choose to resend
        )

        processing_time = (time.time() - start_time) * 1000

        if isinstance(result_data, dict):
            result_data["recreated"] = True

        # Update the new JobLog with the result
        new_job_log.status = "completed"
        new_job_log.response_data = result_data
        new_job_log.duration_ms = int(processing_time)
        await db.commit()

        return {
            "success": True,
            "original_job_id": job_id,
            "new_job_id": new_job_id,
            "processing_time_ms": int(processing_time),
            "response_data": result_data,
            "callback_url": job_log.callback_url,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()

        # Mark the new job as failed if it was created
        try:
            new_job_log.status = "failed"
            new_job_log.error_message = str(e)
            new_job_log.duration_ms = int((time.time() - start_time) * 1000)
            await db.commit()
        except Exception:
            pass

        raise HTTPException(status_code=500, detail=f"Failed to redo job: {str(e)}")


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
    """Send a human-written response replacing the output field, sending to callback_url.
    Also saves the message to MTM as 'supportResponse'."""
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
    
    # Save to MTM as supportResponse
    try:
        import uuid as uuid_mod
        from app.models.conversation_message import ConversationMessage

        request_data = job_log.request_data or {}
        mtm_agent_id = request_data.get("agent_id")
        mtm_session_id = request_data.get("session_id")

        if mtm_agent_id and mtm_session_id:
            msg = ConversationMessage(
                id=uuid_mod.uuid4(),
                agent_id=uuid_mod.UUID(str(mtm_agent_id)),
                session_id=str(mtm_session_id),
                role="supportResponse",
                content=human_text,
            )
            db.add(msg)
            # commit is done below together with response_data update
    except Exception as e:
        logger.error(f"Failed to save supportResponse to MTM: {e}")
    
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


@router.post("/jobs/{job_id}/pause-agent")
async def pause_agent_for_job(
    job_id: str,
    body: dict = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Pause the agent for the session_id associated with this job.
    Body: { "timeout_minutes": 30 } for temporary, or {} / omit for fixed pause.
    """
    body = body or {}
    query = select(JobLog).where(JobLog.job_id == job_id)
    result = await db.execute(query)
    job_log = result.scalar_one_or_none()

    if not job_log:
        raise HTTPException(status_code=404, detail="Job not found")

    request_data = job_log.request_data or {}
    session_id = request_data.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="Job has no session_id in request_data")

    timeout_minutes = body.get("timeout_minutes")
    mode = "fixed"

    if timeout_minutes and int(timeout_minutes) > 0:
        await redis_client.set_agent_pause(session_id, int(timeout_minutes))
        mode = "temporary"
    else:
        await redis_client.set_agent_pause(session_id)

    return {
        "status": "paused",
        "session_id": session_id,
        "mode": mode,
        "timeout_minutes": timeout_minutes if mode == "temporary" else None,
    }


@router.post("/jobs/{job_id}/activate-agent")
async def activate_agent_for_job(
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Reactivate the agent for the session_id associated with this job."""
    query = select(JobLog).where(JobLog.job_id == job_id)
    result = await db.execute(query)
    job_log = result.scalar_one_or_none()

    if not job_log:
        raise HTTPException(status_code=404, detail="Job not found")

    request_data = job_log.request_data or {}
    session_id = request_data.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="Job has no session_id in request_data")

    was_paused = await redis_client.is_agent_paused(session_id)
    await redis_client.remove_agent_pause(session_id)

    return {
        "status": "active",
        "session_id": session_id,
        "was_paused": was_paused,
    }



# ─────────────────────────────────────────────────
# SSE (Server-Sent Events) - Real-time job updates
# ─────────────────────────────────────────────────

@router.get("/stream")
async def stream_job_updates(request: Request):
    """SSE endpoint that streams real-time job status updates via Redis PubSub"""
    async def event_generator():
        client = await redis_client.connect()
        pubsub = client.pubsub(ignore_subscribe_messages=True)
        await pubsub.subscribe("job_updates")
        logger.info("SSE client connected on /tracking/stream")
        
        last_heartbeat = asyncio.get_event_loop().time()
        heartbeat_interval = 15.0  # seconds
        
        try:
            while True:
                if await request.is_disconnected():
                    logger.info("SSE client disconnected from /tracking/stream")
                    break
                
                # Fetch next message with a timeout to prevent blocking indefinitely
                message = await pubsub.get_message(timeout=1.0)
                if message:
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode()
                    yield f"data: {data}\n\n"
                
                # Periodic heartbeat to trigger write failures on disconnected clients
                now = asyncio.get_event_loop().time()
                if now - last_heartbeat >= heartbeat_interval:
                    yield ": heartbeat\n\n"
                    last_heartbeat = now
                    
        except asyncio.CancelledError:
            logger.info("SSE streaming task cancelled")
        except Exception as e:
            logger.error(f"SSE stream error: {e}")
        finally:
            try:
                await pubsub.unsubscribe("job_updates")
                await pubsub.close()
                logger.info("SSE resources cleaned up successfully")
            except Exception as clean_err:
                logger.error(f"Error cleaning up SSE pubsub: {clean_err}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
