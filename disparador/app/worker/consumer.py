import json
import logging
import asyncio
import aio_pika
from sqlalchemy.future import select

from app.database import async_session_maker
from app.models.dispatcher_config import DispatcherConfig
from app.services.rabbitmq_service import disparador_rmq
from app.services.redis_service import disparador_redis
from app.services.dispatcher_engine import dispatch_batch, dispatch_contact

logger = logging.getLogger(__name__)

# Track local tasks for cancellation by triplet key
# triplet_key: f"{type_id}:{queue_id}:{service_id}"
active_tasks = {}

async def process_dispatch_message(message: aio_pika.IncomingMessage):
    """
    Processes a dispatch job with idempotency and replacement logic.
    - If status is 'waiting', replaces the previous job.
    - If status is 'sending' or 'completed', ignores the new job.
    """
    async with message.process():
        try:
            body_str = message.body.decode()
            payload = json.loads(body_str)
            
            type_id = payload.get("type_id")
            queue_id = payload.get("queue_id")
            service_id = payload.get("service_id")
            callback_url = payload.get("callback_url")
            context_data = payload.get("context_data")
            transition_data = payload.get("transition_data")
            timestamp_create = payload.get("timestamp_create")
            
            triplet_key = f"{type_id}:{queue_id}:{service_id}"
            
            # 1. State Check (Idempotency and Replacement logic)
            status = await disparador_redis.get_dispatch_status(triplet_key)
            
            if status in ["sending", "completed"]:
                logger.info(f"Job {triplet_key} already in '{status}' state. Ignoring update.")
                return

            if status == "waiting":
                logger.info(f"Job {triplet_key} is in 'waiting' state. Cancelling previous task to replace.")
                # Local cancellation
                old_task = active_tasks.get(triplet_key)
                if old_task:
                    old_task.cancel()
                
                # Signal cancellation (useful if multi-worker, or to ensure clean break)
                await disparador_redis.signal_cancel(triplet_key)

            # 2. Register current task
            current_task = asyncio.current_task()
            active_tasks[triplet_key] = current_task
            
            # This handles both a batch or a single contact republication inside "contact" vs "contacts"
            contacts = payload.get("contacts", [])
            single_contact = payload.get("contact")
            if single_contact and not contacts:
                contacts = [single_contact]
                
            config_path = payload.get("config_path")
            
            if not config_path:
                logger.error(f"Missing config_path in payload")
                active_tasks.pop(triplet_key, None)
                return

            # Busca Config
            async with async_session_maker() as db:
                query = select(DispatcherConfig).where(DispatcherConfig.path == config_path)
                res = await db.execute(query)
                config = res.scalar_one_or_none()
                
                if not config:
                    logger.error(f"Dispatcher config for path {config_path} not found")
                    active_tasks.pop(triplet_key, None)
                    return
                    
                if not config.is_active:
                    logger.info(f"Dispatcher config for {config_path} is inactive. Skipping.")
                    active_tasks.pop(triplet_key, None)
                    return

            try:
                # 3. Execute Dispatch
                await dispatch_batch(
                    config, type_id, queue_id, contacts, service_id, 
                    context_data, transition_data, callback_url,
                    timestamp_create=timestamp_create
                )
            except asyncio.CancelledError:
                # Expected when a newer job replaces this one
                logger.info(f"Task for {triplet_key} gracefully cancelled.")
                raise # Re-raise to allow cleanup if needed
            finally:
                # 4. Cleanup task registry
                if active_tasks.get(triplet_key) == current_task:
                    active_tasks.pop(triplet_key, None)

        except asyncio.CancelledError:
            # Re-raise to let 'async with message.process()' handle it if needed
            # but usually we want to return from the callback
            return
        except Exception as e:
            logger.error(f"Error processing dispatch message for {service_id}: {e}")
            # Ensure cleanup on error
            if 'triplet_key' in locals() and active_tasks.get(triplet_key) == asyncio.current_task():
                active_tasks.pop(triplet_key, None)

async def start_consumer():

    base_delay = 5
    max_delay = 60
    delay = base_delay

    while True:
        try:
            logger.info("Initializing Disparador Worker...")
            await disparador_rmq.connect()
            await disparador_redis.connect()
            
            if not disparador_rmq.channel:
                raise Exception("RabbitMQ channel not open")

            # We need to discover queues disp_*
            # For this simple worker, we'll assume the webhook API tells it or it listens to a common queue
            # Wait, RabbitMQ doesn't let us wildcard consume queues directly.
            # IN THE PLAN: we declare disp_{type_id}_{queue_id}.
            # Actually, to consume dynamic queues we should probably either route them to a single exchange
            # OR we can just have the worker consume a generic queue "disp_worker" and bind it.
            # Since the plan said publish to disp_{type_id}_{queue_id}, we need to fetch all queues
            # But the webhook already provides contacts. We should probably just use ONE queue for the worker
            # let's simplify to 'disp_main_queue' for the payloads, but we want routing to separate queues if we need prioritization.
            # We'll use a single queue "disp_jobs" for this MVP, or listen to amq.rabbitmq.trace?
            # Let's adjust slightly: we use a single queue `disp_jobs` for the worker, and we queue the batches there.
            
            queue = await disparador_rmq.channel.declare_queue("disp_jobs", durable=True)
            await queue.consume(process_dispatch_message)
            
            logger.info("Started consuming Disparador messages")
            
            # Keep alive
            if disparador_rmq.connection:
                close_event = asyncio.Event()

                def on_close(*_args, **_kwargs):
                    close_event.set()

                disparador_rmq.connection.close_callbacks.add(on_close)
                await close_event.wait()
                logger.warning("RabbitMQ closed. Reconnecting...")
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Disparador consumer err: {e}")
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)
