"""
Agent Control Endpoints — Human Takeover & Agent Pause
Handles fromMe (WhatsApp human response) and agent activation/deactivation.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from app.redis_client import redis_client
from app.database import async_session_maker

router = APIRouter()


class HumanResponseRequest(BaseModel):
    """Payload sent by n8n when a human responds via WhatsApp (fromMe)."""
    session_id: str = Field(..., description="Session identifier (user phone/id)")
    agent_id: str = Field(..., description="Agent ID to associate the message with")
    fromMe: bool = Field(..., description="Must be true to indicate human response")
    message: str = Field(..., description="Content of the human message")
    timeout_minutes: Optional[int] = Field(
        None,
        description="If provided, agent pauses temporarily and reactivates after this many minutes. If omitted, pause is permanent until manual reactivation."
    )

    model_config = {"extra": "allow"}


class ActiveAgentRequest(BaseModel):
    """Payload to reactivate an agent for a session."""
    session_id: str = Field(..., description="Session identifier")
    active: bool = Field(..., description="Must be true to reactivate the agent")


@router.post("/humanResponse")
async def human_response(request: HumanResponseRequest):
    """
    Receive a human response from WhatsApp (via n8n).
    - Saves the message to MTM (PostgreSQL) with role='fromMe'
    - Pauses the agent for this session_id (temporary or fixed)
    """
    if not request.fromMe:
        raise HTTPException(status_code=400, detail="fromMe must be true")

    import uuid as uuid_mod

    # 1. Save message to MTM as 'fromMe'
    try:
        from app.models.conversation_message import ConversationMessage

        async with async_session_maker() as db:
            msg = ConversationMessage(
                id=uuid_mod.uuid4(),
                agent_id=uuid_mod.UUID(str(request.agent_id)),
                session_id=str(request.session_id),
                role="fromMe",
                content=request.message,
            )
            db.add(msg)
            await db.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save message to MTM: {str(e)}")

    # 2. Activate agent pause in Redis
    mode = "fixed"
    expires_in = None
    try:
        if request.timeout_minutes and request.timeout_minutes > 0:
            await redis_client.set_agent_pause(request.session_id, request.timeout_minutes)
            mode = "temporary"
            expires_in = request.timeout_minutes
        else:
            await redis_client.set_agent_pause(request.session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set agent pause: {str(e)}")

    return {
        "status": "paused",
        "session_id": request.session_id,
        "mode": mode,
        "expires_in_minutes": expires_in,
        "message_saved": True,
    }


@router.post("/activeAgent")
async def activate_agent(request: ActiveAgentRequest):
    """
    Reactivate an agent for a session_id.
    Removes the agent_pause key from Redis.
    """
    if not request.active:
        raise HTTPException(status_code=400, detail="active must be true")

    try:
        is_paused = await redis_client.is_agent_paused(request.session_id)
        await redis_client.remove_agent_pause(request.session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove agent pause: {str(e)}")

    return {
        "status": "active",
        "session_id": request.session_id,
        "was_paused": is_paused,
    }
