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

active_tasks = {}
MAX_CONCURRENT_CAMPAIGNS = 10
campaign_semaphore = asyncio.Semaphore(MAX_CONCURRENT_CAMPAIGNS)
church_locks: dict[str, asyncio.Lock] = {}

def get_church_lock(church_key: str) -> asyncio.Lock:
    if church_key not in church_locks:
        church_locks[church_key] = asyncio.Lock()
    return church_locks[church_key]

async def process_dispatch_message(message: aio_pika.IncomingMessage):
    async with message.process(ignore_processed=True, requeue=True):
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
            message_text = payload.get("message")
            campaign_key = payload.get("campaign_key") or f"{type_id}:{queue_id}:{service_id}"
            run_id = payload.get("run_id")
            if not run_id:
                run_id = f"legacy_{type_id}_{queue_id}_{service_id}_{int(asyncio.get_running_loop().time() * 1000)}"

            # Church/queue identification for strict rate-limiting per church + endpoint
            church_id = queue_id
            if not church_id and payload.get("campaign_key"):
                parts = payload["campaign_key"].split(":")
                if len(parts) >= 2 and parts[1]:
                    church_id = parts[1]
            if not church_id and isinstance(payload.get("church"), dict):
                church_id = payload["church"].get("queue_id") or payload["church"].get("church_id") or payload["church"].get("id")

            endpoint_name = type_id or payload.get("config_path") or "default"
            church_key = f"{endpoint_name}:{church_id}" if church_id else f"{endpoint_name}:{service_id}"

            current_task = asyncio.current_task()
            active_tasks[run_id] = current_task
            
            # This handles both a batch or a single contact republication inside "contact" vs "contacts"
            contacts = payload.get("contacts", [])
            single_contact = payload.get("contact")
            if single_contact and not contacts:
                contacts = [single_contact]
                
            config_path = payload.get("config_path")
            campaign_total = payload.get("campaign_total")
            
            logger.info(f"[Worker] Processing dispatch message for run_id={run_id}, service_id={service_id}, church_key={church_key}. Contacts count: {len(contacts)}")
            for i, c in enumerate(contacts):
                num = c.get('number') or c.get('phone') or c.get('user_id')
                if not num:
                    logger.warning(f"[Worker] Contact {i} (name='{c.get('name')}') arrived with empty number/phone/user_id. Payload data: {c}")

            if not config_path:
                logger.error(f"Missing config_path in payload")
                active_tasks.pop(run_id, None)
                return

            # Busca Config
            async with async_session_maker() as db:
                query = select(DispatcherConfig).where(DispatcherConfig.path == config_path)
                res = await db.execute(query)
                config = res.scalar_one_or_none()
                
                if not config:
                    logger.error(f"Dispatcher config for path {config_path} not found")
                    active_tasks.pop(run_id, None)
                    return

                if not config.is_active:
                    logger.info(f"Dispatcher config for {config_path} is inactive. Skipping.")
                    active_tasks.pop(run_id, None)
                    return

            # Check if campaign was explicitly deleted
            if await disparador_redis.is_deleted(service_id):
                logger.warning(f"Campaign {service_id} was deleted. Dropping pending message.")
                active_tasks.pop(run_id, None)
                return

            # Concurrency serialization per church + endpoint:
            # Ensures ONLY ONE batch/dispatch is active for the same church on the same endpoint,
            # respecting the configured min_variation/max_variation delay between every contact!
            church_lock = get_church_lock(church_key)

            if church_lock.locked():
                logger.info(
                    f"[Worker] Church '{church_key}' is already actively dispatching. "
                    f"Message run_id={run_id} is waiting in queue for previous batch to complete."
                )

            async with church_lock:
                # Check again if campaign was deleted while waiting in line
                if await disparador_redis.is_deleted(service_id):
                    logger.warning(f"Campaign {service_id} was deleted while waiting. Dropping message.")
                    active_tasks.pop(run_id, None)
                    return

                async with campaign_semaphore:
                    logger.info(f"[Worker] Acquired lock for church '{church_key}'. Starting batch dispatch run_id={run_id}")
                    try:
                        # 3. Execute Dispatch
                        await dispatch_batch(
                            config,
                            type_id,
                            queue_id,
                            contacts,
                            service_id,
                            context_data,
                            transition_data,
                            callback_url,
                            run_id,
                            campaign_key,
                            message_text=message_text,
                            source_payload=payload,
                            timestamp_create=timestamp_create,
                            campaign_total=campaign_total,
                        )
                    except asyncio.CancelledError:
                        logger.info(f"Task for run {run_id} gracefully cancelled.")
                        raise
                    finally:
                        if active_tasks.get(run_id) == current_task:
                            active_tasks.pop(run_id, None)

        except asyncio.CancelledError:
            logger.warning(
                f"[Worker] Message processing for run_id={run_id if 'run_id' in locals() else 'unknown'} "
                f"was CANCELLED. Re-raising to trigger RabbitMQ requeue."
            )
            raise
        except Exception as e:
            logger.error(f"Error processing dispatch message for {service_id if 'service_id' in locals() else 'unknown'}: {e}", exc_info=True)
            if 'run_id' in locals() and active_tasks.get(run_id) == asyncio.current_task():
                active_tasks.pop(run_id, None)

async def start_consumer():

    base_delay = 5
    max_delay = 60
    delay = base_delay

    while True:
        try:
            logger.info("Initializing Disparador Worker...")
            await disparador_rmq.connect()
            await disparador_redis.connect()
            
            from app.services.smart_router import recover_staged_timers
            await recover_staged_timers()

            if not disparador_rmq.channel:
                raise Exception("RabbitMQ channel not open")

            queue = await disparador_rmq.channel.declare_queue("disp_jobs", durable=True)
            # QoS prefetch set to 20 to allow multiple churches to be pulled and processed in parallel
            await disparador_rmq.channel.set_qos(prefetch_count=20)
            await queue.consume(process_dispatch_message)
            
            logger.info("Started consuming Disparador messages (prefetch=20, max_concurrent=10)")

            # Item D: Start stagnant campaign reconciliation watchdog
            from app.services.reconciliation import start_reconciliation_watchdog
            watchdog_task = asyncio.create_task(start_reconciliation_watchdog())
            
            # Keep alive
            if disparador_rmq.connection:
                close_event = asyncio.Event()

                def on_close(*_args, **_kwargs):
                    close_event.set()

                disparador_rmq.connection.close_callbacks.add(on_close)
                await close_event.wait()
                logger.warning("RabbitMQ closed. Reconnecting...")
                
                # Cancel watchdog task
                if not watchdog_task.done():
                    watchdog_task.cancel()

                # Cancel active tasks to prevent duplicate processing on requeue
                for t in active_tasks.values():
                    t.cancel()
                active_tasks.clear()
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Disparador consumer err: {e}")
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)
