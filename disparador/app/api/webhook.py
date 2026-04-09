from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
import json

from app.database import get_db
from app.models.dispatcher_config import DispatcherConfig
from app.schemas import DispatchPayload, DispatchAcceptedResponse
from app.services.rabbitmq_service import disparador_rmq

router = APIRouter()

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
        
    batch_size = config.messages_per_batch if config.messages_per_batch > 0 else 1
    total_contacts = len(payload.contacts)
    
    # Adicionamos "config_path" para o consumer
    payload_dict = payload.model_dump()
    payload_dict["config_path"] = path
    
    contacts = payload_dict.pop("contacts")
    
    # We will publish to disp_jobs with batches
    for i in range(0, total_contacts, batch_size):
        batch_contacts = contacts[i:i+batch_size]
        batch_payload = payload_dict.copy()
        batch_payload["contacts"] = batch_contacts
        
        # Publicar na fila disp_jobs
        await disparador_rmq.connect()
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

    return DispatchAcceptedResponse(
        service_id=payload.service_id,
        queued_count=total_contacts
    )
