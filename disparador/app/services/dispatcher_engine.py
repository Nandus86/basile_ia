import logging
import asyncio
import random
from datetime import datetime
from zoneinfo import ZoneInfo
import httpx
import json

from app.services.redis_service import disparador_redis
from app.services.basile_client import basile_client
from app.services.rabbitmq_service import disparador_rmq

logger = logging.getLogger(__name__)

def parse_time(time_str: str):
    """Parse HH:mm to time object"""
    return datetime.strptime(time_str, "%H:%M").time()

def is_within_time_window(config, transition_data: dict) -> bool:
    tz_name = (transition_data or {}).get("timezone", "UTC")
    try:
        now = datetime.now(ZoneInfo(tz_name))
    except Exception:
        now = datetime.now(ZoneInfo("UTC"))
        
    start = parse_time(config.start_time)
    end = parse_time(config.end_time)
    
    current_time = now.time()
    
    if start <= end:
        return start <= current_time <= end
    else:
        # Crosses midnight
        return start <= current_time or current_time <= end

async def send_progress(url: str, service_id: str, total: int, sent: int, failed: int = 0, status: str = "running"):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            percent = round((sent + failed) / max(total, 1) * 100, 2)
            payload = {
                "service_id": service_id,
                "type": "progress",
                "status": status,
                "total": total,
                "sent": sent,
                "failed": failed,
                "percent": percent,
                "timestamp": datetime.now(ZoneInfo("UTC")).isoformat()
            }
            await client.post(url, json=payload)
    except Exception as e:
        logger.warning(f"Failed to send progress callback to {url}: {e}")

async def dispatch_contact(config, type_id: str, queue_id: str, contact: dict, service_id: str, context_data: dict, transition_data: dict, callback_url: str, batch_position: int, batch_total: int):
    # Rate Limit
    is_allowed = await disparador_redis.check_rate_limit(contact["number"])
    if not is_allowed:
        logger.info(f"Rate limit skipped dispatch for {contact['number']} in {service_id}")
        await disparador_redis.increment_failed(service_id)
        await disparador_redis.add_to_dlq(service_id, contact, "Rate limit: Disparo muito recente para este número")
        return

    # Gera Index
    index = await disparador_redis.get_next_index(str(config.id), service_id, config.index_max)
    
    # ProcessRequest Payload
    agent_payload = {
        "message": "DISPARADOR_START", # Placeholder ou pode ser configurável
        "session_id": f"{contact['number']}_{service_id}",
        "agent_id": str(config.agent_id) if config.agent_id else None,
        "callback_url": callback_url,
        "context_data": {
            **(context_data or {}),
            "contact_name": contact["name"],
            "contact_phone": contact["number"],
            "dispatcher_index": index,
            "dispatcher_triggers": config.triggers,
            "dispatcher_buttons": config.buttons if config.buttons_enabled else [],
            "dispatcher_image_enabled": config.image_enabled,
        },
        "transition_data": transition_data,
    }
    
    target_url = getattr(config, 'target_endpoint', None)
    
    try:
        agent_response = await basile_client.post_to_agent(config.path, agent_payload, custom_url=target_url)
    except Exception as e:
        await disparador_redis.add_to_dlq(service_id, contact, str(e))
        await disparador_redis.increment_failed(service_id)
        return
    
    await disparador_redis.increment_sent(service_id)
    
    # Delay
    delay = random.randint(config.min_variation_seconds, config.max_variation_seconds)
    
    # Warm-up (1.5x delay in first 10%)
    if batch_total > 0 and batch_position < (batch_total * 0.1):
        delay = int(delay * 1.5)
        
    await asyncio.sleep(delay)
    
    # Load balance (0.5 to 1.2s delay for organic exiting)
    lb_delay = random.uniform(0.5, 1.2)
    await asyncio.sleep(lb_delay)

async def dispatch_batch(config, type_id: str, queue_id: str, contacts: list, service_id: str, context_data: dict, transition_data: dict, callback_url: str, timestamp_create: str = None):
    total = len(contacts)
    if total == 0:
        return
        
    triplet_key = f"{type_id}:{queue_id}:{service_id}"
    await disparador_redis.init_campaign(service_id, total, str(config.id), config.path)
    
    # 1. Dynamic Start Delay
    wait_time = config.start_delay_seconds
    if timestamp_create and config.start_delay_seconds > 0:
        try:
            # Assumes ISO format from worker/consumer or previous re-queue
            created_at = datetime.fromisoformat(timestamp_create.replace("Z", "+00:00"))
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            
            now = datetime.now(timezone.utc)
            elapsed = (now - created_at).total_seconds()
            wait_time = max(0, config.start_delay_seconds - elapsed)
            logger.info(f"Campaign {service_id} dynamic wait: {wait_time:.1f}s (Original: {config.start_delay_seconds}s, Elapsed: {elapsed:.1f}s)")
        except Exception as e:
            logger.warning(f"Failed to calculate dynamic delay for {service_id}: {e}")
            wait_time = config.start_delay_seconds

    if wait_time > 0:
        await disparador_redis.set_dispatch_status(triplet_key, "waiting")
        try:
            # We use a simple sleep for now, but consumer can cancel the task
            await asyncio.sleep(wait_time)
        except asyncio.CancelledError:
            logger.info(f"Dispatch task for {triplet_key} CANCELLED during wait.")
            # Status will be cleaned up by the consumer or signal
            raise

    # 2. Check if we should still proceed (idempotency check)
    # If the status is no longer waiting (e.g. was cancelled or replaced), we might be in trouble
    # but the consumer handles the 'sending' block.
    await disparador_redis.set_dispatch_status(triplet_key, "sending")
        
    for i, contact in enumerate(contacts):
        # 3. Check for cancellation/interruption mid-batch (optional but good)
        # In this specific requirement, if it's already "sending", new ones are ignored.
        # But if the user manually pauses/stops, we check that too.
        
        # Pause Check
        while await disparador_redis.is_paused(service_id):
            logger.info(f"Campaign {service_id} is paused. Waiting 5s...")
            await asyncio.sleep(5.0)
            
        # Window Check
        if not is_within_time_window(config, transition_data):
            logger.info(f"Campaign {service_id} out of time window. Requeuing remaining {len(contacts)-i} contacts.")
            # Re-queue others
            for c in contacts[i:]:
                requeue_payload = {
                    "type_id": type_id,
                    "queue_id": queue_id,
                    "service_id": service_id,
                    "contact": c, # note single contact
                    "context_data": context_data,
                    "transition_data": transition_data,
                    "callback_url": callback_url,
                    "timestamp_create": timestamp_create or datetime.now(ZoneInfo("UTC")).isoformat()
                }
                # Publish individual missing messages
                await disparador_rmq.publish_contact(type_id, queue_id, requeue_payload)
            
            # Since we are re-queuing, we clear status so it can be picked up later in the right window
            await disparador_redis.delete_dispatch_status(triplet_key)
            break
            
        await dispatch_contact(config, type_id, queue_id, contact, service_id, context_data, transition_data, callback_url, i, total)
        
        # Progress callback ~10%
        if config.progress_callback_url:
            sent = await disparador_redis.get_sent_count(service_id)
            if sent % max(1, total // 10) == 0:
                # We need failed count too.
                campaign = await disparador_redis.get_campaign(service_id)
                failed = campaign.get("failed", 0) if campaign else 0
                await send_progress(config.progress_callback_url, service_id, total, sent, failed)
                
    # 4. Loop Finished
    await disparador_redis.set_dispatch_status(triplet_key, "completed")
    campaign = await disparador_redis.get_campaign(service_id)
    if campaign:
        if campaign.get("sent", 0) + campaign.get("failed", 0) >= campaign.get("total", 0):
            await disparador_redis.complete_campaign(service_id)
            if config.progress_callback_url:
                await send_progress(config.progress_callback_url, service_id, campaign["total"], campaign["sent"], campaign["failed"], status="completed")

