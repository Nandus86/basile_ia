from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.redis_service import disparador_redis
from app.services.rabbitmq_service import disparador_rmq
from app.schemas import CampaignReport, CampaignStatus
from app.database import get_db
from app.models.dispatcher_config import DispatcherConfig
from sqlalchemy.future import select
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
import json
import uuid
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

class CampaignLockRequest(BaseModel):
    type_id: str
    queue_id: str
    service_id: str

@router.get("/stats")
async def get_dashboard_stats():
    campaigns = await disparador_redis.list_campaigns()
    active = sum(1 for c in campaigns if c.get("status") in ("running", "paused"))
    completed = sum(1 for c in campaigns if c.get("status") == "completed")
    total_sent = sum(c.get("sent", 0) for c in campaigns)
    total_failed = sum(c.get("failed", 0) for c in campaigns)
    # Get RabbitMQ queue status
    mq_pending = 0
    try:
        await disparador_rmq.connect()
        if disparador_rmq.channel:
            queue = await disparador_rmq.channel.declare_queue("disp_jobs", durable=True, passive=True)
            mq_pending = queue.declaration_result.message_count
    except Exception as e:
        logger.warning(f"Failed to get mq_pending: {e}")
    
    return {
        "total_campaigns": len(campaigns),
        "active_campaigns": active,
        "completed_campaigns": completed,
        "total_sent": total_sent,
        "total_failed": total_failed,
        "mq_pending": mq_pending
    }

@router.get("/campaigns")
async def list_campaigns():
    campaigns = await disparador_redis.list_campaigns()
    return campaigns

@router.get("/campaigns/{service_id}")
async def get_campaign_details(service_id: str):
    data = await disparador_redis.get_campaign(service_id)
    if not data:
        raise HTTPException(status_code=404, detail="Campaign not found")
    data["service_id"] = service_id
    data["is_paused"] = await disparador_redis.is_paused(service_id)
    return data

@router.post("/campaigns/{service_id}/pause")
async def pause_campaign(service_id: str):
    await disparador_redis.pause_campaign(service_id)
    return {"message": "Paused successfully"}

@router.post("/campaigns/{service_id}/resume")
async def resume_campaign(service_id: str):
    await disparador_redis.resume_campaign(service_id)

    campaign = await disparador_redis.get_campaign(service_id)
    if campaign:
        campaign_key = campaign.get("campaign_key")
        if campaign_key:
            await disparador_redis.unlock_campaign(campaign_key)

    return {"message": "Resumed successfully"}


@router.post("/campaigns/{service_id}/activate")
async def activate_campaign(service_id: str):
    """Alias for resume to support frontend action naming."""
    return await resume_campaign(service_id)

@router.post("/campaigns/unlock")
async def unlock_campaign_lock(payload: CampaignLockRequest):
    campaign_key = f"{payload.type_id}:{payload.queue_id}:{payload.service_id}"
    await disparador_redis.unlock_campaign(campaign_key)
    return {"campaign_key": campaign_key, "lock": "unlocked"}

@router.post("/campaigns/lock")
async def lock_campaign_lock(payload: CampaignLockRequest):
    campaign_key = f"{payload.type_id}:{payload.queue_id}:{payload.service_id}"
    await disparador_redis.lock_campaign(campaign_key)
    return {"campaign_key": campaign_key, "lock": "locked"}

@router.get("/campaigns/lock-status")
async def campaign_lock_status(type_id: str, queue_id: str, service_id: str):
    campaign_key = f"{type_id}:{queue_id}:{service_id}"
    lock = await disparador_redis.get_campaign_lock(campaign_key)
    last_run = await disparador_redis.get_last_run(campaign_key)
    return {"campaign_key": campaign_key, "lock": lock, "last_run": last_run}

@router.post("/campaigns/{service_id}/retry-dlq")
async def retry_dlq(service_id: str):

    items = await disparador_redis.get_dlq(service_id)
    if not items:
        return {"message": "DLQ is empty", "requeued": 0}
        
    campaign = await disparador_redis.get_campaign(service_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found to get config_path")
        
    # we requeue them as single jobs to disp_jobs
    count = 0
    await disparador_rmq.connect()
    for item in items:
        contact = item["contact"]
        # we reconstruct a dummy payload
        requeue_payload = {
            "type_id": "dlq_retry",
            "queue_id": "dlq_retry",
            "service_id": service_id,
            "contacts": [contact],
            "message": "DISPARADOR_START",
            "callback_url": "",
            "context_data": {},
            "transition_data": {},
            "system": {"apikey": None},
            "dispatch_flags": {"lock_bypass": True},
            "timestamp_create": "",
            "config_path": campaign.get("config_path")
        }
        try:
            queue = await disparador_rmq.channel.declare_queue("disp_jobs", durable=True)
            message = __import__('aio_pika').Message(
                body=json.dumps(requeue_payload).encode(),
                delivery_mode=__import__('aio_pika').DeliveryMode.PERSISTENT
            )
            await disparador_rmq.channel.default_exchange.publish(message, routing_key="disp_jobs")
            count += 1
        except Exception:
            pass
            
    await disparador_redis.clear_dlq(service_id)
    return {"message": "DLQ retry initiated", "requeued": count}

@router.get("/campaigns/{service_id}/report", response_model=CampaignReport)
async def get_campaign_report(service_id: str):
    campaign = await disparador_redis.get_campaign(service_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
        
    total = campaign.get("total", 0)
    sent = campaign.get("sent", 0)
    failed = campaign.get("failed", 0)
    
    success_rate = round((sent / max(total, 1)) * 100, 2)
    dlq_items = await disparador_redis.get_dlq(service_id)
    contacts = await disparador_redis.get_campaign_contacts(service_id)
    debug = await disparador_redis.get_campaign_payloads(service_id)
    
    return CampaignReport(
        service_id=service_id,
        status=campaign.get("status", "unknown"),
        total=total,
        sent=sent,
        failed=failed,
        percent=campaign.get("percent", 0.0),
        started_at=campaign.get("started_at"),
        completed_at=campaign.get("completed_at"),
        success_rate=success_rate,
        dlq_count=len(dlq_items),
        config_id=campaign.get("config_id"),
        config_path=campaign.get("config_path"),
        contacts=contacts,
        debug=debug
    )

@router.get("/staged")
async def get_staged_queues():
    import time
    import json
    await disparador_redis.ensure_connected()
    
    # Scan all deadline keys
    keys = []
    cursor = '0'
    while True:
        cursor, partial_keys = await disparador_redis.client.scan(cursor, match="disp:staged:deadline:global:*", count=100)
        keys.extend(partial_keys)
        if not cursor or cursor == '0' or cursor == 0:
            break
            
    result = []
    now = int(time.time())

    for key in keys:
        key_str = key.decode("utf-8") if isinstance(key, bytes) else str(key)
        queue_id = key_str.split("global:")[-1]

        deadline_raw = await disparador_redis.client.get(key)
        if not deadline_raw:
            continue
            
        deadline = int(deadline_raw)
        time_remaining = max(0, deadline - now)
        
        # Get all staged entries for this queue_id
        index_key = f"disp:staged:index:global:{queue_id}"
        entries = await disparador_redis.client.smembers(index_key)
        
        # Group contacts by type_id
        type_id_map = {}
        total_contacts = 0

        for entry in entries:
            entry_str = entry.decode("utf-8") if isinstance(entry, bytes) else str(entry)
            try:
                config_path, type_id, service_id = entry_str.split(":", 2)
            except ValueError:
                continue

            contacts_key = f"disp:staged:global:{queue_id}:{config_path}:{type_id}:{service_id}"
            raw_contacts = await disparador_redis.client.lrange(contacts_key, 0, -1)

            contacts = []
            for rc in raw_contacts:
                try:
                    c = json.loads(rc)
                    contacts.append(c)
                except Exception:
                    pass

            total_contacts += len(contacts)

            if type_id not in type_id_map:
                type_id_map[type_id] = {
                    "type_id": type_id,
                    "service_id": service_id,
                    "config_path": config_path,
                    "contacts": [],
                    "contact_count": 0,
                }

            type_id_map[type_id]["contacts"].extend(contacts)
            type_id_map[type_id]["contact_count"] += len(contacts)
            
        result.append({
            "queue_id": queue_id,
            "deadline": deadline,
            "time_remaining": time_remaining,
            "time_remaining_minutes": time_remaining // 60,
            "time_remaining_seconds": time_remaining % 60,
            "total_contacts": total_contacts,
            "type_ids": list(type_id_map.values()),
        })
        
    return result

@router.post("/campaigns/{service_id}/recreate")
async def recreate_campaign(service_id: str, db: AsyncSession = Depends(get_db)):
    # 1. Get campaign metadata
    campaign = await disparador_redis.get_campaign(service_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
        
    config_path = campaign.get("config_path")
    if not config_path:
        raise HTTPException(status_code=400, detail="config_path not found in campaign metadata")
        
    # 2. Get dispatcher config from DB
    query = select(DispatcherConfig).where(DispatcherConfig.path == config_path)
    result = await db.execute(query)
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Dispatcher config not found for this path")
        
    # 3. Retrieve original cached input payload
    payloads = await disparador_redis.get_campaign_payloads(service_id)
    if not payloads or "input" not in payloads:
        raise HTTPException(status_code=404, detail="Original payload not found in cache")
        
    input_payload = payloads["input"]
    
    # 4. Retrieve campaign contacts
    contacts = await disparador_redis.get_campaign_contacts(service_id)
    if not contacts:
        raise HTTPException(status_code=404, detail="No contacts found for this campaign")
        
    cleaned_contacts = []
    for c in contacts:
        cleaned_c = {k: v for k, v in c.items() if k not in {"status", "updated_at", "error"}}
        cleaned_contacts.append(cleaned_c)
        
    # 5. Cancel any active run for the old campaign (if running)
    campaign_key = campaign.get("campaign_key")
    if campaign_key:
        await disparador_redis.unlock_campaign(campaign_key)
        last_run = await disparador_redis.get_last_run(campaign_key)
        if last_run:
            await disparador_redis.signal_cancel(last_run)
            await disparador_redis.set_run_status(last_run, "cancelled")
            
    # 6. Wipe Redis metrics for the old campaign (so we start completely fresh)
    await disparador_redis.client.delete(f"disp:campaign:{service_id}")
    await disparador_redis.client.delete(f"disp:campaign:contacts:{service_id}")
    await disparador_redis.client.delete(f"disp:campaign:payloads:{service_id}")
    await disparador_redis.client.delete(f"disp:dlq:{service_id}")
    await disparador_redis.client.delete(f"disp:paused:{service_id}")
    
    # 7. Build fresh campaign trigger payload
    # Let's ensure "dispatch_flags" has "lock_bypass": True and a specific flag "recreate": True
    recreate_payload = dict(input_payload)
    dispatch_flags = recreate_payload.get("dispatch_flags") or {}
    if not isinstance(dispatch_flags, dict):
        dispatch_flags = {}
    dispatch_flags["lock_bypass"] = True
    dispatch_flags["recreate"] = True
    recreate_payload["dispatch_flags"] = dispatch_flags
    recreate_payload["contacts"] = cleaned_contacts
    
    # 8. Re-enqueue to RabbitMQ (disp_jobs) using fresh run_id
    run_id = uuid.uuid4().hex
    batch_size = config.messages_per_batch if config.messages_per_batch > 0 else 1
    total_contacts = len(cleaned_contacts)
    
    # Keep the same campaign_key so it matches but bypass lock
    if not campaign_key:
        campaign_key = f"{recreate_payload.get('type_id')}:{recreate_payload.get('queue_id')}:{service_id}"
        
    recreate_payload["config_path"] = config_path
    recreate_payload["campaign_key"] = campaign_key
    recreate_payload["run_id"] = run_id
    
    # Extract contacts for batching
    payload_dict = dict(recreate_payload)
    contacts_list = payload_dict.pop("contacts")
    
    await disparador_rmq.connect()
    for i in range(0, total_contacts, batch_size):
        batch_contacts = contacts_list[i:i+batch_size]
        batch_payload = payload_dict.copy()
        batch_payload["contacts"] = batch_contacts
        
        try:
            queue = await disparador_rmq.channel.declare_queue("disp_jobs", durable=True)
            message = __import__('aio_pika').Message(
                body=json.dumps(batch_payload).encode(),
                delivery_mode=__import__('aio_pika').DeliveryMode.PERSISTENT
            )
            await disparador_rmq.channel.default_exchange.publish(
                message,
                routing_key="disp_jobs"
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro ao enfileirar na recriação: {e}")
            
    # Set lock and run status
    await disparador_redis.lock_campaign(campaign_key)
    await disparador_redis.set_last_run(campaign_key, run_id)
    
    return {"message": "Campanha recriada e disparada com sucesso", "new_run_id": run_id}

@router.post("/campaigns/{service_id}/delete")
async def delete_campaign(service_id: str):
    # 1. Get campaign metadata
    campaign = await disparador_redis.get_campaign(service_id)
    if campaign:
        campaign_key = campaign.get("campaign_key")
        if campaign_key:
            # Unlock the campaign
            await disparador_redis.unlock_campaign(campaign_key)
            # Cancel active run (if running)
            last_run = await disparador_redis.get_last_run(campaign_key)
            if last_run:
                await disparador_redis.signal_cancel(last_run)
                await disparador_redis.set_run_status(last_run, "cancelled")
                
    # 2. Wipe Redis keys for the campaign
    await disparador_redis.client.delete(f"disp:campaign:{service_id}")
    await disparador_redis.client.delete(f"disp:campaign:contacts:{service_id}")
    await disparador_redis.client.delete(f"disp:campaign:payloads:{service_id}")
    await disparador_redis.client.delete(f"disp:dlq:{service_id}")
    await disparador_redis.client.delete(f"disp:paused:{service_id}")
    
    # 3. Clean up any staged queues that match this service_id
    if campaign:
        queue_id = campaign.get("queue_id")
        if queue_id:
            await disparador_redis.client.delete(f"disp:staged:deadline:global:{queue_id}")
            await disparador_redis.client.delete(f"disp:staged:index:global:{queue_id}")
            
            # Delete keys matching "disp:staged:global:{queue_id}:*"
            cursor = '0'
            while True:
                cursor, keys = await disparador_redis.client.scan(cursor, match=f"disp:staged:global:{queue_id}:*", count=100)
                for k in keys:
                    await disparador_redis.client.delete(k)
                if not cursor or cursor == '0' or cursor == 0:
                    break
                    
    return {"message": "Campanha e filas excluídas e limpas com sucesso"}

class RedispatchContactRequest(BaseModel):
    contact: dict

@router.post("/campaigns/{service_id}/redispatch-contact")
async def redispatch_contact(service_id: str, payload: RedispatchContactRequest, db: AsyncSession = Depends(get_db)):
    """Redispatch a single contact from an existing campaign."""
    contact = payload.contact

    # 1. Get campaign metadata
    campaign = await disparador_redis.get_campaign(service_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    config_path = campaign.get("config_path")
    if not config_path:
        raise HTTPException(status_code=400, detail="config_path not found in campaign metadata")

    # 2. Get dispatcher config from DB
    query = select(DispatcherConfig).where(DispatcherConfig.path == config_path)
    result = await db.execute(query)
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Dispatcher config not found for this path")

    # 3. Retrieve original cached input payload for context
    payloads = await disparador_redis.get_campaign_payloads(service_id)
    input_payload = payloads.get("input", {}) if payloads else {}

    campaign_key = campaign.get("campaign_key", f"redispatch:{service_id}")

    # 4. Build single-contact job payload
    # Clean contact metadata added by the tracking system
    cleaned_contact = {k: v for k, v in contact.items() if k not in {"status", "updated_at", "error"}}

    redispatch_payload = {
        "type_id": input_payload.get("type_id", "redispatch"),
        "queue_id": input_payload.get("queue_id", "redispatch"),
        "service_id": service_id,
        "contacts": [cleaned_contact],
        "message": input_payload.get("message", "DISPARADOR_START"),
        "callback_url": input_payload.get("callback_url", ""),
        "context_data": input_payload.get("context_data", {}),
        "transition_data": input_payload.get("transition_data", {}),
        "system": input_payload.get("system", {"apikey": None}),
        "config_path": config_path,
        "campaign_key": campaign_key,
        "run_id": uuid.uuid4().hex,
        "dispatch_flags": {"lock_bypass": True},
        "timestamp_create": "",
    }

    # Copy global and church data if available in original payload
    for key in ("global", "church"):
        if key in input_payload:
            redispatch_payload[key] = input_payload[key]

    # 5. Enqueue to RabbitMQ
    await disparador_rmq.connect()
    try:
        queue = await disparador_rmq.channel.declare_queue("disp_jobs", durable=True)
        message = __import__('aio_pika').Message(
            body=json.dumps(redispatch_payload).encode(),
            delivery_mode=__import__('aio_pika').DeliveryMode.PERSISTENT
        )
        await disparador_rmq.channel.default_exchange.publish(message, routing_key="disp_jobs")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao enfileirar redispatch: {e}")

    # 6. Reset contact status in Redis
    contact_number = contact.get("number") or contact.get("phone") or contact.get("user_id")
    if contact_number:
        await disparador_redis.update_contact_status(service_id, contact_number, "pending")

    return {"message": f"Contato {contact.get('name', '')} reenfileirado com sucesso", "run_id": redispatch_payload["run_id"]}
