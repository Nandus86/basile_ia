from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.redis_service import disparador_redis
from app.services.rabbitmq_service import disparador_rmq
from app.schemas import CampaignReport, CampaignStatus
import json

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
    
    return {
        "total_campaigns": len(campaigns),
        "active_campaigns": active,
        "completed_campaigns": completed,
        "total_sent": total_sent,
        "total_failed": total_failed
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
