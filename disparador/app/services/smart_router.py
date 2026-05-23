"""
Smart Queue Router — Roteamento Inteligente por Queue ID
Acumula listas do mesmo queue_id e despacha em round-robin ponderado por porcentagem.
"""
import json
import math
import uuid
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.services.redis_service import disparador_redis
from app.services.rabbitmq_service import disparador_rmq

logger = logging.getLogger(__name__)

# Active routing timers (prevent duplicates)
_active_timers: Dict[str, asyncio.Task] = {}


async def recover_staged_timers():
    """Recover and restart timers for staged global queues from Redis on startup."""
    import time
    await disparador_redis.ensure_connected()
    logger.info("Starting recovery of global Smart Routing timers...")

    cursor = '0'
    keys = []
    while True:
        cursor, partial_keys = await disparador_redis.client.scan(cursor, match="disp:staged:deadline:global:*", count=100)
        keys.extend(partial_keys)
        if not cursor or cursor == '0' or cursor == 0:
            break

    now = int(time.time())
    recovered_count = 0

    for key in keys:
        key_str = key.decode("utf-8") if isinstance(key, bytes) else str(key)
        queue_id = key_str.split("global:")[-1]
        
        deadline_raw = await disparador_redis.client.get(key)
        if not deadline_raw:
            continue
            
        deadline = int(deadline_raw)
        time_remaining = max(0, deadline - now)
        
        if time_remaining <= 0:
            logger.info("Timer for queue %s expired while offline. Executing immediately.", queue_id)
            asyncio.create_task(execute_routing(queue_id))
            recovered_count += 1
        else:
            logger.info("Recovered timer for queue %s. Re-arming for %d seconds.", queue_id, time_remaining)
            await _schedule_routing_timer(queue_id, time_remaining)
            recovered_count += 1
            
    logger.info("Recovered %d global Smart Routing timers.", recovered_count)


async def stage_contacts(
    config_path: str,
    queue_id: str,
    type_id: str,
    service_id: str,
    contacts: list,
    payload_meta: dict,
    accumulation_seconds: int = 60,
):
    """
    Stage contacts in Redis for smart routing globally by queue_id.
    Starts or resets the global accumulation timer for this queue_id.
    """
    await disparador_redis.ensure_connected()

    # Store contacts
    contacts_key = f"disp:staged:global:{queue_id}:{config_path}:{type_id}:{service_id}"
    for contact in contacts:
        await disparador_redis.client.rpush(contacts_key, json.dumps(contact))
    await disparador_redis.client.expire(contacts_key, 86400)  # 24h TTL

    # Store payload metadata
    meta_key = f"disp:staged:meta:global:{queue_id}:{config_path}:{type_id}:{service_id}"
    await disparador_redis.client.set(meta_key, json.dumps(payload_meta), ex=86400)

    # Track this combination for this global queue_id
    index_key = f"disp:staged:index:global:{queue_id}"
    entry = f"{config_path}:{type_id}:{service_id}"
    await disparador_redis.client.sadd(index_key, entry)
    await disparador_redis.client.expire(index_key, 86400)

    logger.info(
        "Staged %d contacts for global routing: path=%s queue=%s type=%s service=%s (timer=%ds)",
        len(contacts), config_path, queue_id, type_id, service_id, accumulation_seconds,
    )

    # Start accumulation timer (does not reset if running)
    await _schedule_routing_timer(queue_id, accumulation_seconds)


async def _schedule_routing_timer(queue_id: str, seconds: int):
    """Start the global accumulation timer for a queue_id."""
    timer_key = f"global:{queue_id}"

    # Do not reset existing timer if any
    existing = _active_timers.get(timer_key)
    if existing and not existing.done():
        logger.debug("Accumulation timer for %s already running, not resetting", timer_key)
        return

    await disparador_redis.ensure_connected()
    deadline = int(datetime.now(timezone.utc).timestamp()) + seconds
    deadline_key = f"disp:staged:deadline:global:{queue_id}"
    await disparador_redis.client.set(deadline_key, deadline, ex=86400)

    # Create new timer
    async def _timer():
        try:
            await asyncio.sleep(seconds)
            logger.info("Global accumulation timer expired for %s — starting routing", timer_key)
            await execute_routing(queue_id)
        except asyncio.CancelledError:
            pass
        finally:
            _active_timers.pop(timer_key, None)

    _active_timers[timer_key] = asyncio.create_task(_timer())


async def check_daily_limit(queue_id: str, limit: int) -> int:
    """
    Check how many messages can still be sent today globally for this queue_id.
    """
    if limit <= 0:
        return -1  # unlimited

    await disparador_redis.ensure_connected()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"disp:daily:global:{queue_id}:{today}"
    current = int(await disparador_redis.client.get(key) or 0)
    return max(0, limit - current)


async def increment_daily_count(queue_id: str, count: int = 1):
    """Increment the global daily message counter."""
    await disparador_redis.ensure_connected()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"disp:daily:global:{queue_id}:{today}"
    await disparador_redis.client.incrby(key, count)
    await disparador_redis.client.expire(key, 172800)  # 48h


async def execute_routing(queue_id: str):
    """
    Main global routing logic. Called when the global accumulation timer expires.
    
    1. Collects all staged type_ids for this queue_id across all config_paths.
    2. Loads the configs and determines the max daily limit.
    3. Normalizes percentages if sum > 100%.
    4. Builds weighted round-robin dispatch plan.
    5. Publishes batches to RabbitMQ in interleaved order.
    """
    lock_key = f"disp:routing:active:global:{queue_id}"
    await disparador_redis.ensure_connected()

    # Acquire routing lock
    acquired = await disparador_redis.client.set(lock_key, "1", nx=True, ex=600)
    if not acquired:
        logger.warning("Routing already active for global queue_id %s — skipping", queue_id)
        return

    try:
        # 1. Collect all staged entries
        index_key = f"disp:staged:index:global:{queue_id}"
        entries = await disparador_redis.client.smembers(index_key)

        if not entries:
            logger.info("No staged entries for global queue_id %s", queue_id)
            return

        # Extract unique config_paths
        config_paths = list(set(entry.split(":")[0] for entry in entries))

        # 2. Load configs from DB
        from app.database import async_session_maker
        from sqlalchemy.future import select
        from app.models.dispatcher_config import DispatcherConfig

        configs = {}
        async with async_session_maker() as db:
            query = select(DispatcherConfig).where(DispatcherConfig.path.in_(config_paths))
            result = await db.execute(query)
            for cfg in result.scalars():
                configs[cfg.path] = cfg

        if not configs:
            logger.error("No configs found for staged paths during routing of %s", queue_id)
            return

        # Determine global max daily limit
        max_daily_limit = 0
        for cfg in configs.values():
            limit = cfg.daily_message_limit or 0
            if limit > max_daily_limit:
                max_daily_limit = limit

        # 3. Build staged lists
        staged_lists = {}
        for entry in entries:
            config_path, type_id, service_id = entry.split(":", 2)
            contacts_key = f"disp:staged:global:{queue_id}:{config_path}:{type_id}:{service_id}"
            meta_key = f"disp:staged:meta:global:{queue_id}:{config_path}:{type_id}:{service_id}"

            raw_contacts = await disparador_redis.client.lrange(contacts_key, 0, -1)
            contacts = [json.loads(c) for c in raw_contacts]

            raw_meta = await disparador_redis.client.get(meta_key)
            meta = json.loads(raw_meta) if raw_meta else {}

            if not contacts:
                continue

            cfg = configs.get(config_path)
            routing_rules = cfg.queue_routing_rules or [] if cfg else []
            rule = next((r for r in routing_rules if r["type_id"] == type_id), None)
            
            percentage = rule["percentage"] if rule else 100

            staged_lists[entry] = {
                "config_path": config_path,
                "type_id": type_id,
                "service_id": service_id,
                "contacts": contacts,
                "percentage": percentage,
                "meta": meta,
                "label": rule.get("label", type_id) if rule else type_id,
            }

        if not staged_lists:
            logger.info("All staged lists empty for global queue_id %s", queue_id)
            return

        # 4. Normalize percentages if total > 100%
        total_pct = sum(info["percentage"] for info in staged_lists.values())
        if total_pct > 100:
            for info in staged_lists.values():
                info["percentage"] = (info["percentage"] / total_pct) * 100

        # 5. Check daily limit
        remaining_quota = await check_daily_limit(queue_id, max_daily_limit)

        # 6. Build dispatch plan (round-robin cycles)
        cycles = _build_dispatch_plan(staged_lists, remaining_quota)

        total_messages = sum(
            len(contact_batch) for cycle in cycles for _, contact_batch, _ in cycle
        )
        logger.info(
            "Global Smart Routing plan for queue_id %s — %d cycles, %d total messages, %d staged lists",
            queue_id, len(cycles), total_messages, len(staged_lists),
        )

        # 7. Publish each cycle as batches to RabbitMQ
        run_id = uuid.uuid4().hex
        await disparador_rmq.connect()

        for cycle_idx, cycle in enumerate(cycles):
            for entry_key, contact_batch, meta in cycle:
                config_path, type_id, service_id = entry_key.split(":", 2)

                batch_payload = {
                    **meta,
                    "type_id": type_id,
                    "queue_id": queue_id,
                    "service_id": service_id,
                    "contacts": contact_batch,
                    "config_path": config_path,
                    "campaign_key": f"{type_id}:{queue_id}:{service_id}",
                    "run_id": f"{run_id}_c{cycle_idx}_{type_id}",
                    "dispatch_flags": {"lock_bypass": True},
                    "_smart_routing": {
                        "cycle": cycle_idx + 1,
                        "total_cycles": len(cycles),
                        "queue_id": queue_id,
                    },
                }

                try:
                    queue = await disparador_rmq.channel.declare_queue("disp_jobs", durable=True)
                    import aio_pika
                    message = aio_pika.Message(
                        body=json.dumps(batch_payload).encode(),
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    )
                    await disparador_rmq.channel.default_exchange.publish(
                        message, routing_key="disp_jobs"
                    )
                except Exception as e:
                    logger.error("Failed to publish smart routing batch: %s", e)

        # 8. Increment global daily counter
        if total_messages > 0:
            await increment_daily_count(queue_id, total_messages)

        # 9. Cleanup staged data
        for entry in entries:
            config_path, type_id, service_id = entry.split(":", 2)
            await disparador_redis.client.delete(
                f"disp:staged:global:{queue_id}:{config_path}:{type_id}:{service_id}"
            )
            await disparador_redis.client.delete(
                f"disp:staged:meta:global:{queue_id}:{config_path}:{type_id}:{service_id}"
            )
        await disparador_redis.client.delete(index_key)
        await disparador_redis.client.delete(f"disp:staged:deadline:global:{queue_id}")

        logger.info("Global Smart Routing completed for %s — %d messages queued", queue_id, total_messages)

    except Exception as e:
        logger.error("Smart Routing error for global queue_id %s: %s", queue_id, e, exc_info=True)
    finally:
        await disparador_redis.client.delete(lock_key)


def _build_dispatch_plan(
    staged_lists: dict,
    remaining_quota: int,
) -> List[List[tuple]]:
    """
    Build weighted round-robin dispatch cycles.
    
    Each cycle contains one batch per type_id, sized by its percentage.
    Continues cycling until all contacts are exhausted or quota is reached.
    
    Returns: List of cycles, where each cycle is a list of
             (entry_key, contact_batch, meta) tuples.
    """
    # Calculate batch size per type_id
    batches_info = {}
    for entry_key, info in staged_lists.items():
        total = len(info["contacts"])
        pct = info["percentage"]
        batch_size = max(1, math.ceil(total * pct / 100))
        # Cap batch size to 10 to prevent RabbitMQ consumer timeout
        batch_size = min(batch_size, 10)
        batches_info[entry_key] = {
            "remaining": list(info["contacts"]),
            "batch_size": batch_size,
            "meta": info["meta"],
        }

    cycles = []
    total_queued = 0
    max_iterations = 100000  # safety for large lists

    for _ in range(max_iterations):
        cycle = []
        cycle_has_contacts = False

        for entry_key, batch_data in batches_info.items():
            remaining = batch_data["remaining"]
            if not remaining:
                continue

            # Check quota
            if remaining_quota >= 0:
                available = remaining_quota - total_queued
                if available <= 0:
                    logger.warning("Daily limit reached during plan building")
                    if cycle:
                        cycles.append(cycle)
                    return cycles

            batch_size = min(batch_data["batch_size"], len(remaining))

            # If quota limited, cap the batch
            if remaining_quota >= 0:
                batch_size = min(batch_size, remaining_quota - total_queued)

            if batch_size <= 0:
                continue

            contact_batch = remaining[:batch_size]
            batch_data["remaining"] = remaining[batch_size:]
            total_queued += len(contact_batch)

            cycle.append((entry_key, contact_batch, batch_data["meta"]))
            cycle_has_contacts = True

        if not cycle_has_contacts:
            break

        cycles.append(cycle)

    return cycles
