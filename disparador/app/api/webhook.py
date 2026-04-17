from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
import json
import uuid
import logging

from app.database import get_db
from app.models.dispatcher_config import DispatcherConfig
from app.schemas import DispatchPayload, DispatchAcceptedResponse
from app.services.rabbitmq_service import disparador_rmq
from app.services.redis_service import disparador_redis

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/trigger/personalizado/{path:path}", response_model=DispatchAcceptedResponse)
async def receive_dispatch(path: str, payload: DispatchPayload, db: AsyncSession = Depends(get_db)):
    query = select(DispatcherConfig).where(DispatcherConfig.path == path)
    result = await db.execute(query)
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
        
    if not config.is_active:
        raise HTTPException(status_code=400, detail="Config is inactive")
        
    incoming_key = payload.system.apikey if payload.system else None
    if config.api_key and incoming_key != config.api_key:
        raise HTTPException(status_code=403, detail="Invalid API Key")
        
    campaign_key = f"{payload.type_id}:{payload.queue_id}:{payload.service_id}"
    dispatch_flags = payload.model_dump().get("dispatch_flags") or {}
    lock_bypass = bool(dispatch_flags.get("lock_bypass", False))

    if not lock_bypass and await disparador_redis.is_campaign_locked(campaign_key):
        run_status = None
        last_run = await disparador_redis.get_last_run(campaign_key)
        if last_run:
            run_status = await disparador_redis.get_run_status(last_run)

        # Auto-heal stale lock when there is no active run.
        if run_status not in ("waiting", "sending"):
            logger.warning(
                "Auto-unlocking stale campaign lock for %s (last_run=%s, run_status=%s)",
                campaign_key,
                last_run,
                run_status,
            )
            await disparador_redis.unlock_campaign(campaign_key)
        else:
            raise HTTPException(status_code=409, detail="Campaign is locked for re-dispatch")

    run_id = uuid.uuid4().hex
    batch_size = config.messages_per_batch if config.messages_per_batch > 0 else 1
    total_contacts = len(payload.contacts)

    payload_dict = payload.model_dump()
    payload_dict["config_path"] = path
    payload_dict["campaign_key"] = campaign_key
    payload_dict["run_id"] = run_id

    contacts = payload_dict.pop("contacts")

    await disparador_rmq.connect()
    for i in range(0, total_contacts, batch_size):
        batch_contacts = contacts[i:i+batch_size]
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
            raise HTTPException(status_code=500, detail=f"Erro ao enfileirar: {e}")

    if not lock_bypass:
        await disparador_redis.lock_campaign(campaign_key)
    await disparador_redis.set_last_run(campaign_key, run_id)

    return DispatchAcceptedResponse(
        service_id=payload.service_id,
        campaign_key=campaign_key,
        run_id=run_id,
        queued_count=total_contacts
    )
