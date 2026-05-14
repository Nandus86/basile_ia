from fastapi import APIRouter, Depends, HTTPException, Header
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
from app.services.smart_router import stage_contacts, check_daily_limit

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/trigger/personalizado/{path:path}", response_model=DispatchAcceptedResponse)
async def receive_dispatch(
    path: str, 
    payload: DispatchPayload, 
    x_api_key: str = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db)
):
    query = select(DispatcherConfig).where(DispatcherConfig.path == path)
    result = await db.execute(query)
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
        
    if not config.is_active:
        raise HTTPException(status_code=400, detail="Config is inactive")
        
    if config.api_key and x_api_key != config.api_key:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    
    # Queue ID filter
    allowlist = config.queue_id_allowlist or []
    blocklist = config.queue_id_blocklist or []
    if allowlist:
        if payload.queue_id not in allowlist:
            raise HTTPException(status_code=403, detail=f"Queue ID '{payload.queue_id}' não está na lista de permitidos")
    elif blocklist:
        if payload.queue_id in blocklist:
            raise HTTPException(status_code=403, detail=f"Queue ID '{payload.queue_id}' está bloqueado")

    # Smart Queue Routing — check if this type_id has a routing rule
    routing_rules = config.queue_routing_rules or []
    if routing_rules:
        rule = next((r for r in routing_rules if r.get("type_id") == payload.type_id), None)
        if rule:
            # Check daily limit before staging
            daily_limit = config.daily_message_limit or 0
            if daily_limit > 0:
                remaining = await check_daily_limit(path, payload.queue_id, daily_limit)
                if remaining == 0:
                    raise HTTPException(
                        status_code=429,
                        detail=f"Limite diário de {daily_limit} mensagens atingido para queue_id '{payload.queue_id}'"
                    )

            total_contacts = len(payload.contacts)
            payload_dict = payload.model_dump()
            contacts = payload_dict.pop("contacts")
            payload_dict.pop("system", None)  # remove system from meta
            
            campaign_key = f"{payload.type_id}:{payload.queue_id}:{payload.service_id}"

            await stage_contacts(
                config_path=path,
                queue_id=payload.queue_id,
                type_id=payload.type_id,
                service_id=payload.service_id,
                contacts=contacts,
                payload_meta=payload_dict,
                accumulation_seconds=config.routing_accumulation_seconds or 60,
            )

            return DispatchAcceptedResponse(
                service_id=payload.service_id,
                campaign_key=campaign_key,
                run_id=f"staged_{uuid.uuid4().hex[:8]}",
                queued_count=total_contacts,
                status="staged"
            )

    # Normal flow (no routing rules or type_id not in rules)
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

