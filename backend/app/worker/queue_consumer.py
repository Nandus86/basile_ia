"""
RabbitMQ Consumer Worker for Webhook Processing
"""
import asyncio
import json
import logging
import aio_pika

from app.services.rabbitmq_service import rabbitmq_client
from app.database import async_session_maker
from app.orchestrator import run_orchestrator_v2
from app.redis_client import redis_client

logger = logging.getLogger(__name__)

# Controla as tasks rodando por job para podermos interceder via sinal de abort
active_jobs = {}


async def _publish_job_update(job_id, status, webhook_path=None, request_data=None, response_data=None, error_message=None, duration_ms=None, created_at=None):
    """Publish a job status update to the SSE Redis channel for real-time frontend updates."""
    try:
        session_id = None
        if request_data and isinstance(request_data, dict):
            session_id = request_data.get("session_id")
        await redis_client.publish("job_updates", json.dumps({
            "event": "job_updated",
            "data": {
                "job_id": job_id,
                "webhook_path": webhook_path or "",
                "status": status,
                "request_data": request_data,
                "response_data": response_data,
                "error_message": error_message,
                "duration_ms": duration_ms,
                "created_at": created_at,
                "completed_at": None,
            }
        }))
    except Exception:
        pass

async def _listen_for_aborts():
    """Background task to listen for abort signals via Redis PubSub."""
    import asyncio
    try:
        # Pega a connection nativa do banco gerida pela class do redis_client
        client = await redis_client.connect()
        pubsub = client.pubsub()
        await pubsub.subscribe("job_control")
        logger.info("Listening for job aborts on Redis PubSub channel 'job_control'")
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = message["data"]
                # No redis.asyncio o data pode vir como bytes ou srt dependendo do encoding
                if isinstance(data, bytes):
                    data = data.decode()
                
                if data.startswith("abort:"):
                    job_to_abort = data.split(":", 1)[1]
                    logger.warning(f"Recebido pedido de ABORT para o job: {job_to_abort}")
                    task = active_jobs.get(job_to_abort)
                    if task:
                        logger.warning(f"Cancelando task do job {job_to_abort} imediatamente!")
                        task.cancel()
                    else:
                        logger.info(f"Job {job_to_abort} nao esta ativo neste worker.")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error in pubsub abort listener: {e}")

async def _save_to_mtm(agent_id: str, session_id: str, role: str, content: str):
    """Helper to save a message to MTM (PostgreSQL ConversationMessage)."""
    try:
        import uuid as uuid_mod
        from app.models.conversation_message import ConversationMessage
        async with async_session_maker() as db_session:
            msg = ConversationMessage(
                id=uuid_mod.uuid4(),
                agent_id=uuid_mod.UUID(str(agent_id)),
                session_id=str(session_id),
                role=role,
                content=content,
            )
            db_session.add(msg)
            await db_session.commit()
    except Exception as e:
        logger.error(f"Failed to save {role} message to MTM: {e}")


async def _mark_job_status(job_id: str, status: str, payload: dict = None, error_msg: str = None):
    """Helper to update JobLog status and publish SSE event."""
    try:
        from sqlalchemy.future import select
        from app.models.job_log import JobLog
        from datetime import datetime, timezone
        async with async_session_maker() as db_session:
            query = select(JobLog).where(JobLog.job_id == job_id)
            res = await db_session.execute(query)
            job_log = res.scalar_one_or_none()
            if job_log:
                job_log.status = status
                if error_msg:
                    job_log.error_message = error_msg
                job_log.completed_at = datetime.now(timezone.utc)
                if job_log.created_at:
                    job_log.duration_ms = int((job_log.completed_at - job_log.created_at).total_seconds() * 1000)
                await db_session.commit()
                await _publish_job_update(
                    job_id=job_id, status=status,
                    webhook_path=job_log.webhook_path,
                    request_data=payload,
                    error_message=error_msg,
                    duration_ms=job_log.duration_ms,
                    created_at=job_log.created_at.isoformat() if job_log.created_at else None,
                )
    except Exception:
        pass


async def process_webhook_message(message: aio_pika.IncomingMessage):
    """Callback to process a message from RabbitMQ.
    
    Includes two guard layers:
    1. Agent Pause Check — if agent is paused for this session, save msg to MTM and skip.
    2. Concurrency Guard — if another job is active for this session, buffer msg in Redis.
    
    After processing, drains any buffered messages and re-publishes as a single combined job.
    """
    async with message.process():
        lock_acquired = False
        session_id = None
        job_id = None
        body = None

        try:
            body = json.loads(message.body.decode())
            payload = body.get("payload", {})
            config_id = body.get("webhook_config_id")
            session_id = body.get("session_id")
            job_id = body.get("job_id")

            logger.info(f"Processing webhook job {job_id} for session {session_id}")

            # Prepare args for orchestrator
            message_text = payload.get("message")
            agent_id = payload.get("agent_id")
            user_access_level = payload.get("user_access_level", "normal")
            context_data = payload.get("context_data")
            transition_data = payload.get("transition_data")
            callback_url = payload.get("callback_url")

            # ═══════════════════════════════════════════════════════
            # GUARD 1: Agent Pause Check
            # ═══════════════════════════════════════════════════════
            if session_id and await redis_client.is_agent_paused(session_id):
                logger.info(f"[Guard] Agent is PAUSED for session {session_id}. Saving to MTM and skipping job {job_id}.")

                # Save the user's message to MTM so it's not lost
                if message_text and agent_id:
                    await _save_to_mtm(agent_id, session_id, "user", message_text)

                # Mark job as paused
                await redis_client.set(
                    f"job:{job_id}",
                    json.dumps({"job_id": job_id, "status": "paused", "result": None}),
                    expire=3600
                )
                await _mark_job_status(job_id, "paused", payload)
                return

            # ═══════════════════════════════════════════════════════
            # GUARD 2: Concurrency Guard (Lock)
            # ═══════════════════════════════════════════════════════
            if session_id and job_id:
                lock_acquired = await redis_client.acquire_user_lock(session_id, job_id)

                if not lock_acquired:
                    logger.info(f"[Guard] Session {session_id} is LOCKED (another job active). Buffering job {job_id}.")

                    # Buffer the essential payload for later processing
                    buffer_data = json.dumps({
                        "message": message_text,
                        "agent_id": agent_id,
                        "context_data": context_data,
                        "transition_data": transition_data,
                        "callback_url": callback_url,
                        "user_access_level": user_access_level,
                        "original_job_id": job_id,
                    })
                    await redis_client.push_to_buffer(session_id, buffer_data)

                    # Mark job as buffered
                    await redis_client.set(
                        f"job:{job_id}",
                        json.dumps({"job_id": job_id, "status": "buffered", "result": None}),
                        expire=3600
                    )
                    await _mark_job_status(job_id, "buffered", payload)
                    return

            # ═══════════════════════════════════════════════════════
            # MAIN PROCESSING (original logic, unchanged)
            # ═══════════════════════════════════════════════════════
            if job_id:
                active_jobs[job_id] = asyncio.current_task()

            # Set to in_progress
            await redis_client.set(
                f"job:{job_id}",
                json.dumps({
                    "job_id": job_id,
                    "status": "in_progress",
                    "result": None
                }),
                expire=3600
            )

            try:
                from sqlalchemy.future import select
                from app.models.job_log import JobLog
                async with async_session_maker() as db_session:
                    query = select(JobLog).where(JobLog.job_id == job_id)
                    res = await db_session.execute(query)
                    job_log = res.scalar_one_or_none()
                    if job_log:
                        job_log.status = "in_progress"
                        await db_session.commit()
                        # SSE: publish job update
                        await _publish_job_update(
                            job_id=job_id, status="in_progress",
                            webhook_path=job_log.webhook_path,
                            request_data=payload,
                            created_at=job_log.created_at.isoformat() if job_log.created_at else None,
                        )
            except Exception as e:
                logger.error(f"Failed to update JobLog in_progress: {e}")

            async with async_session_maker() as db:
                from app.orchestrator.agent_factory import AgentFactory
                from langchain_core.messages import HumanMessage, AIMessage

                # Check if target agent exists and has output schema
                agent_config = None
                agent = None
                logger.info(f"[Consumer] agent_id={agent_id}, session={session_id}")
                
                factory = AgentFactory(db)
                if agent_id:
                    agent = await factory.get_agent_by_id(agent_id)
                    logger.info(f"[Consumer] Agent found: {agent.name if agent else 'None'}, has output_schema: {bool(agent.output_schema) if agent else False}")
                    
                    if agent:
                        # Auto-map extra root fields from payload to context or transition data
                        standard_keys = {"message", "session_id", "agent_id", "user_access_level", "metadata", "context_data", "transition_data", "callback_url", "source", "event_type", "sender_id", "sender_name", "timestamp"}
                        ctx_keys = set(agent.input_schema.keys()) if agent.input_schema else set()
                        trans_keys = set(agent.transition_input_schema.keys()) if agent.transition_input_schema else set()
                        
                        c_data = context_data or {}
                        t_data = transition_data or {}
                        
                        for k, v in payload.items():
                            if k in standard_keys: continue
                            # Se estiver estritamente no schema de transição do entry-agent, vai para transition_data
                            if k in trans_keys:
                                t_data[k] = v
                            else:
                                # Todo o resto vai para context_data para que tanto o orquestrador 
                                # quanto os subordinados possam buscar o que for necessário em seus próprios schemas
                                c_data[k] = v
                                
                        if c_data: context_data = c_data
                        if t_data: transition_data = t_data

                    if agent:
                        logger.info(f"[Consumer] Agent found: {agent.name}")
                else:
                    logger.warning(f"[Consumer] No agent_id provided, falling back to standard orchestrator")

                # Configure resilience
                max_retries = 3
                retry_delay = 1.0
                if agent and agent.resilience_config:
                    max_retries = agent.resilience_config.max_retries
                    retry_delay = getattr(agent.resilience_config, "retry_delay_seconds", 1.0)
                
                attempts = 0
                last_exception = None
                
                # Start StatusMonitor for interim progress messages
                monitor = None
                if callback_url and agent:
                    from app.worker.status_monitor import StatusMonitor
                    monitor = StatusMonitor(
                        callback_url=callback_url,
                        agent_config={
                            "status_updates_enabled": getattr(agent, "status_updates_enabled", True),
                            "status_updates_config": getattr(agent, "status_updates_config", {}) or {}
                        },
                        session_id=session_id,
                        transition_data=transition_data, # Use reconstructed transition data
                        is_structured=bool(agent.output_schema)
                    )
                    await monitor.start()
                    # Initial state is handled by the loop delay
                
                while attempts <= max_retries:
                    attempts += 1
                    try:
                        from app.worker.tasks import process_message_task
                        
                        logger.info(f"[Consumer] Delegating to unified process_message_task")
                        response_data = await process_message_task(
                            ctx={},
                            message=message_text,
                            session_id=session_id,
                            agent_id=agent_id,
                            user_access_level=user_access_level,
                            context_data=context_data,
                            transition_data=None, # Passed later
                            callback_url=None     # Handled later by consumer loop
                        )
                        
                        if response_data.get("status") == "failed":
                            raise Exception(response_data.get("error", "Unknown error in process_message_task"))
                            
                        # process_message_task handles STM internally
                        
                        # Extract final result
                        if "output" in response_data:
                            # Structured using output
                            final_result = {k: v for k, v in response_data.items() if k not in ["status", "agent_used", "processing_time_ms", "transition_data"]}
                        elif "response" in response_data:
                            # Standard text response
                            final_result = response_data["response"]
                        else:
                            # Other structured formats
                            final_result = {k: v for k, v in response_data.items() if k not in ["status", "agent_used", "processing_time_ms", "transition_data"]}
                            
                        agent_used = response_data.get("agent_used")
                        
                        # If execution succeeded, break retry loop
                        break

                    except Exception as e:
                        last_exception = e
                        logger.error(f"[Consumer] Attempt {attempts}/{max_retries+1} failed: {str(e)}")
                        if attempts <= max_retries:
                            logger.info(f"[Consumer] Retrying in {retry_delay} seconds...")
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                        else:
                            logger.error(f"[Consumer] All {max_retries+1} attempts failed for job {job_id}.")
                            raise last_exception
                
                # Stop StatusMonitor — processing complete
                if monitor:
                    await monitor.stop()
                
            # Set to completed
            job_data = {
                "job_id": job_id,
                "status": "completed",
                "result": final_result,
                "agent_used": agent_used
            }
            if transition_data:
                job_data["transition_data"] = transition_data

            await redis_client.set(
                f"job:{job_id}",
                json.dumps(job_data),
                expire=3600
            )

            try:
                from sqlalchemy.future import select
                from app.models.job_log import JobLog
                from datetime import datetime, timezone
                async with async_session_maker() as db_session:
                    query = select(JobLog).where(JobLog.job_id == job_id)
                    res = await db_session.execute(query)
                    job_log = res.scalar_one_or_none()
                    if job_log:
                        job_log.status = "completed"
                        # Salvar payload completo (mesmo que vai para o callback)
                        full_response_data = {
                            "status": "completed",
                            "job_id": job_id,
                            "result": final_result if not isinstance(final_result, dict) else final_result.get("output", final_result.get("response", str(final_result))),
                            "agent_used": agent_used
                        }
                        if transition_data:
                            full_response_data["transition_data"] = transition_data
                        job_log.response_data = full_response_data
                        job_log.completed_at = datetime.now(timezone.utc)
                        if job_log.created_at:
                            job_log.duration_ms = int((job_log.completed_at - job_log.created_at).total_seconds() * 1000)
                        await db_session.commit()
                        # SSE: publish job completed
                        await _publish_job_update(
                            job_id=job_id, status="completed",
                            webhook_path=job_log.webhook_path,
                            request_data=payload,
                            response_data=full_response_data,
                            duration_ms=job_log.duration_ms,
                            created_at=job_log.created_at.isoformat() if job_log.created_at else None,
                        )
            except Exception as e:
                logger.error(f"Failed to update JobLog completed: {e}")

            logger.info(f"Successfully processed webhook job {job_id}, result type: {type(final_result).__name__}")

            if callback_url:
                import httpx
                try:
                    async with httpx.AsyncClient() as client:
                        response_data = {
                            "status": "completed",
                            "job_id": job_id,
                            "result": final_result,
                            "agent_used": agent_used
                        }
                        
                        if transition_data:
                            response_data["transition_data"] = transition_data
                            
                        await client.post(callback_url, json=response_data, timeout=10.0)
                        logger.info(f"Callback sent to {callback_url}")
                except Exception as cb_err:
                    logger.error(f"Failed to send callback to {callback_url}: {str(cb_err)}")

        except Exception as e:
            logger.error(f"Error processing webhook job from RabbitMQ: {str(e)}")
            # Stop monitor on error
            if 'monitor' in locals() and monitor:
                try:
                    await monitor.stop()
                except Exception:
                    pass
            job_id = body.get("job_id") if body else None
            if job_id:
                try:
                    await redis_client.set(
                        f"job:{job_id}",
                        json.dumps({
                            "job_id": job_id,
                            "status": "failed",
                            "error": str(e)
                        }),
                        expire=3600
                    )
                    from sqlalchemy.future import select
                    from app.models.job_log import JobLog
                    from datetime import datetime, timezone
                    async with async_session_maker() as db_session:
                        query = select(JobLog).where(JobLog.job_id == job_id)
                        res = await db_session.execute(query)
                        job_log = res.scalar_one_or_none()
                        if job_log:
                            job_log.status = "failed"
                            job_log.error_message = str(e)
                            job_log.completed_at = datetime.now(timezone.utc)
                            if job_log.created_at:
                                job_log.duration_ms = int((job_log.completed_at - job_log.created_at).total_seconds() * 1000)
                            await db_session.commit()
                            # SSE: publish job failed
                            await _publish_job_update(
                                job_id=job_id, status="failed",
                                webhook_path=job_log.webhook_path,
                                request_data=body.get("payload", {}),
                                error_message=str(e),
                                duration_ms=job_log.duration_ms,
                                created_at=job_log.created_at.isoformat() if job_log.created_at else None,
                            )
                except Exception:
                    pass

        except asyncio.CancelledError:
            logger.warning(f"Job {job_id} task was CANCELLED/ABORTED")
            # Stop monitor on cancel
            if 'monitor' in locals() and monitor:
                try:
                    await monitor.stop()
                except Exception:
                    pass
            job_id = body.get("job_id") if body else None
            if job_id:
                try:
                    await redis_client.set(
                        f"job:{job_id}",
                        json.dumps({
                            "job_id": job_id,
                            "status": "failed",
                            "error": "Aborted by user"
                        }),
                        expire=3600
                    )
                    from sqlalchemy.future import select
                    from app.models.job_log import JobLog
                    from datetime import datetime, timezone
                    async with async_session_maker() as db_session:
                        query = select(JobLog).where(JobLog.job_id == job_id)
                        res = await db_session.execute(query)
                        job_log = res.scalar_one_or_none()
                        if job_log:
                            job_log.status = "failed"
                            job_log.error_message = "Aborted by user"
                            job_log.completed_at = datetime.now(timezone.utc)
                            if job_log.created_at:
                                job_log.duration_ms = int((job_log.completed_at - job_log.created_at).total_seconds() * 1000)
                            await db_session.commit()
                            # SSE: publish job aborted
                            await _publish_job_update(
                                job_id=job_id, status="failed",
                                webhook_path=job_log.webhook_path,
                                request_data=body.get("payload", {}),
                                error_message="Aborted by user",
                                duration_ms=job_log.duration_ms,
                                created_at=job_log.created_at.isoformat() if job_log.created_at else None,
                            )
                except Exception:
                    pass
            # Devemos retornar normalmente para que aio_pika considere a msg processada e nao entre em loop
            return
            
        finally:
            # ═══════════════════════════════════════════════════════
            # DRAIN BUFFER & RELEASE LOCK
            # ═══════════════════════════════════════════════════════
            if job_id and job_id in active_jobs:
                active_jobs.pop(job_id, None)

            if lock_acquired and session_id:
                try:
                    # Check if agent was paused DURING processing (human took over)
                    if await redis_client.is_agent_paused(session_id):
                        logger.info(f"[Guard] Agent was paused during processing of {job_id}. Releasing lock without draining buffer.")
                        await redis_client.release_user_lock(session_id)
                    else:
                        # Drain buffer — check for accumulated messages
                        buffered_items = await redis_client.drain_buffer(session_id)

                        if buffered_items:
                            logger.info(f"[Guard] Draining {len(buffered_items)} buffered messages for session {session_id}")

                            # Combine messages into a single text
                            combined_parts = []
                            # Use the first buffered item's metadata for the new job
                            first_item = json.loads(buffered_items[0])
                            new_agent_id = first_item.get("agent_id")
                            new_callback_url = first_item.get("callback_url")
                            new_context_data = first_item.get("context_data")
                            new_transition_data = first_item.get("transition_data")
                            new_user_access_level = first_item.get("user_access_level", "normal")

                            for i, item_json in enumerate(buffered_items):
                                item = json.loads(item_json)
                                msg = item.get("message", "")
                                if msg:
                                    combined_parts.append(f"Mensagem {i+1}: \"{msg}\"")

                            combined_message = (
                                "[O usuário enviou mensagens adicionais enquanto o atendimento anterior estava em andamento]\n\n"
                                + "\n".join(combined_parts)
                            )

                            # Re-publish as a new job to RabbitMQ (lock stays active)
                            import uuid as uuid_mod
                            new_job_id = f"job_{uuid_mod.uuid4().hex}"

                            new_payload = {
                                "message": combined_message,
                                "agent_id": new_agent_id,
                                "session_id": session_id,
                                "user_access_level": new_user_access_level,
                                "context_data": new_context_data,
                                "transition_data": new_transition_data,
                                "callback_url": new_callback_url,
                            }

                            # Create JobLog for the new combined job
                            try:
                                from app.models.job_log import JobLog
                                async with async_session_maker() as db_session:
                                    job_log = JobLog(
                                        job_id=new_job_id,
                                        webhook_path="buffer_drain",
                                        status="queued",
                                        request_data=new_payload,
                                        callback_url=new_callback_url,
                                    )
                                    db_session.add(job_log)
                                    await db_session.commit()
                            except Exception as e:
                                logger.error(f"[Guard] Failed to create JobLog for drained job: {e}")

                            # Publish to RabbitMQ
                            from app.services.rabbitmq_service import rabbitmq_client as rmq
                            success = await rmq.publish_webhook_job(
                                payload=new_payload,
                                config_id="buffer_drain",
                                session_id=session_id,
                                job_id=new_job_id,
                            )
                            if success:
                                logger.info(f"[Guard] Re-published drained buffer as new job {new_job_id}")
                            else:
                                logger.error(f"[Guard] Failed to re-publish drained buffer!")
                                await redis_client.release_user_lock(session_id)
                        else:
                            # No buffer — simply release lock
                            await redis_client.release_user_lock(session_id)
                            logger.info(f"[Guard] Lock released for session {session_id}")
                except Exception as guard_err:
                    logger.error(f"[Guard] Error in drain/release: {guard_err}")
                    # Safety: always release lock on error
                    try:
                        await redis_client.release_user_lock(session_id)
                    except Exception:
                        pass

async def start_rabbitmq_consumer():
    """
    Start listening to the webhook queue with automatic reconnection.
    Runs an infinite loop that reconnects on connection loss with exponential backoff.
    """
    base_delay = 5
    max_delay = 60
    delay = base_delay

    while True:
        try:
            logger.info("Initializing RabbitMQ consumer...")

            # Force a fresh connection each iteration
            rabbitmq_client.channel = None
            rabbitmq_client.connection = None
            await rabbitmq_client.connect()

            # Start abort listener (only once per connection loop is fine, or keep it running outside)
            abort_task = asyncio.create_task(_listen_for_aborts())

            if not rabbitmq_client.channel:
                logger.error(f"Failed to connect to RabbitMQ. Retrying in {delay}s...")
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)
                continue

            # Reset delay on successful connection
            delay = base_delay

            queue = await rabbitmq_client.channel.get_queue(rabbitmq_client.webhook_queue_name)
            await queue.consume(process_webhook_message)
            logger.info(f"Started consuming messages from {rabbitmq_client.webhook_queue_name}")

            # Keep alive: wait until the connection closes
            # aio_pika.RobustConnection emits closing; we await it
            if rabbitmq_client.connection:
                close_event = asyncio.Event()

                def on_close(*_args, **_kwargs):
                    close_event.set()

                rabbitmq_client.connection.close_callbacks.add(on_close)
                await close_event.wait()
                logger.warning("RabbitMQ connection closed. Reconnecting...")
                abort_task.cancel()

        except asyncio.CancelledError:
            logger.info("Consumer task cancelled, shutting down.")
            break
        except Exception as e:
            logger.error(f"RabbitMQ consumer error: {e}. Reconnecting in {delay}s...")
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)
