from fastapi import APIRouter, HTTPException
from typing import List

from app.services.redis_service import disparador_redis
from app.services.rabbitmq_service import disparador_rmq
from app.schemas import CampaignReport, CampaignStatus
import json

router = APIRouter()

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
    return {"message": "Resumed successfully"}

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
            "callback_url": "", # We might lose original callback_url if not stored in DLQ, usually we should.
            "context_data": {},
            "transition_data": {},
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
        config_path=campaign.get("config_path")
    )
