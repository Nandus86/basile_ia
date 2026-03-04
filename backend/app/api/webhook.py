"""
Webhook Endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import time
import uuid

from app.database import get_db
from app.redis_client import get_redis, RedisClient
from app.services.rabbitmq_service import rabbitmq_client
from app.models.webhook_config import WebhookConfig
from app.schemas.webhook import (
    WebhookRequest, WebhookResponse,
    ProcessRequest, ProcessResponse,
    AsyncProcessResponse, JobStatusResponse
)
from app.orchestrator import run_orchestrator_v2

router = APIRouter()


@router.post("/receive", response_model=WebhookResponse)
async def receive_webhook(
    request: WebhookRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """
    Receive webhook events from external sources.
    Stores the event and returns acknowledgment.
    """
    try:
        # Store message in conversation history
        await redis.add_message(
            session_id=request.sender_id,
            role="user",
            content=request.message
        )
        
        return WebhookResponse(
            success=True,
            message="Webhook received successfully",
            data={
                "source": request.source,
                "sender_id": request.sender_id,
                "event_type": request.event_type
            }
        )
    except Exception as e:
        return WebhookResponse(
            success=False,
            message=f"Error processing webhook: {str(e)}"
        )




@router.post("/process", response_model=ProcessResponse)
async def process_message(
    request: ProcessRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """
    Process a message synchronously and return AI response.
    Uses the LangGraph Supervisor orchestrator with multi-agent support.
    """
    start_time = time.time()
    
    # Set request context for deep services (MCP tools)
    from app.context import set_request_context
    if request.context_data:
        print(f"[Webhook] 📥 Received context_data: {request.context_data}")
        set_request_context(request.context_data)
    else:
        set_request_context({})
    
    try:
        # Get conversation history
        history = await redis.get_conversation(request.session_id)
        
        # Add current message to history
        await redis.add_message(
            session_id=request.session_id,
            role="user",
            content=request.message
        )
        
        # Run the supervisor orchestrator (v2)
        result = await run_orchestrator_v2(
            message=request.message,
            session_id=request.session_id,
            history=history,
            agent_id=request.agent_id,
            db=db,
            user_access_level=request.user_access_level,
            context_data=request.context_data
        )
        
        # Store response in history
        await redis.add_message(
            session_id=request.session_id,
            role="assistant",
            content=result["response"]
        )
        
        processing_time = (time.time() - start_time) * 1000
        
        return ProcessResponse(
            response=result["response"],
            agent_used=result.get("agent_used"),
            processing_time_ms=processing_time
        )
        
    except Exception as e:
        processing_time = (time.time() - start_time) * 1000
        return ProcessResponse(
            response=f"Error processing message: {str(e)}",
            processing_time_ms=processing_time
        )


@router.post("/process/structured")
async def process_message_structured(
    request: ProcessRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """
    Process a message and return structured JSON output.
    Uses the agent's output_schema if defined, otherwise uses default schema.
    
    Example response with custom schema:
    {
        "output": "Resposta aqui",
        "tag": "coletando",
        "agent_used": "Vendas",
        "processing_time_ms": 1234.5
    }
    """
    from app.orchestrator.agent_factory import AgentFactory
    from langchain_core.messages import HumanMessage, AIMessage
    
    start_time = time.time()
    
    try:
        # Get conversation history
        history = await redis.get_conversation(request.session_id)
        
        # Add current message to history
        await redis.add_message(
            session_id=request.session_id,
            role="user",
            content=request.message
        )
        
        # Initialize factory
        factory = AgentFactory(db)
        
        # Get agent
        if request.agent_id:
            agent = await factory.get_agent_by_id(request.agent_id)
        else:
            agents = await factory.get_accessible_agents(request.user_access_level)
            agent = agents[0] if agents else None
        
        if not agent:
            processing_time = (time.time() - start_time) * 1000
            return {
                "output": "Nenhum agente disponível.",
                "agent_used": None,
                "processing_time_ms": processing_time
            }
        
        # Get agent config
        agent_config = await factory.get_agent_config(agent)
        
        # Build messages
        messages = []
        for msg in history:
            if msg.get("role") == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg.get("role") == "assistant":
                messages.append(AIMessage(content=msg["content"]))
        messages.append(HumanMessage(content=request.message))
        
        # Get RAG context if available
        rag_context = None
        try:
            from app.services.rag_service import get_rag_context
            rag_context = await get_rag_context(db, agent_config["id"], request.message, limit=5)
        except Exception:
            pass
        
        # Invoke with structured output
        result = await factory.invoke_agent_structured(
            agent_config=agent_config,
            messages=messages,
            rag_context=rag_context,
            context_data=request.context_data
        )
        
        # Store response in history
        output_text = result.get("output", str(result))
        await redis.add_message(
            session_id=request.session_id,
            role="assistant",
            content=output_text
        )
        
        processing_time = (time.time() - start_time) * 1000
        
        # Return structured response with metadata
        return {
            **result,
            "agent_used": agent_config["name"],
            "processing_time_ms": processing_time
        }
        
    except Exception as e:
        processing_time = (time.time() - start_time) * 1000
        return {
            "output": f"Erro: {str(e)}",
            "error": str(e),
            "processing_time_ms": processing_time
        }


@router.post("/process/async", response_model=AsyncProcessResponse)
async def process_message_async(
    request: ProcessRequest,
    redis: RedisClient = Depends(get_redis)
):
    """
    Enqueue a message for asynchronous processing.
    Returns immediately with a job_id that can be polled for results.
    
    Use GET /webhook/jobs/{job_id} to check the status.
    """
    from app.worker.queue_client import enqueue_process_message
    
    try:
        job_id = await enqueue_process_message(
            message=request.message,
            session_id=request.session_id,
            agent_id=request.agent_id,
            user_access_level=request.user_access_level,
            context_data=request.context_data,
            transition_data=request.transition_data,
            callback_url=request.callback_url,
        )
        
        return AsyncProcessResponse(
            job_id=job_id,
            status="queued",
            message="Job enfileirado com sucesso"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao enfileirar job: {str(e)}")


@router.post("/process/structured/async", response_model=AsyncProcessResponse)
async def process_message_structured_async(
    request: ProcessRequest,
    redis: RedisClient = Depends(get_redis)
):
    """
    Enqueue a structured processing job.
    Returns immediately with a job_id that can be polled for results.
    """
    from app.worker.queue_client import enqueue_process_structured
    
    try:
        job_id = await enqueue_process_structured(
            message=request.message,
            session_id=request.session_id,
            agent_id=request.agent_id,
            user_access_level=request.user_access_level,
            context_data=request.context_data,
            transition_data=request.transition_data,
            callback_url=request.callback_url,
        )
        
        return AsyncProcessResponse(
            job_id=job_id,
            status="queued",
            message="Job estruturado enfileirado com sucesso"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao enfileirar job: {str(e)}")


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status_endpoint(job_id: str):
    """
    Check the status of an async job.
    
    Statuses:
    - queued: waiting to be picked up by a worker
    - in_progress: currently being processed
    - completed: finished, result available
    - failed: failed after retries
    - not_found: job ID not recognized
    """
    from app.worker.queue_client import get_job_status
    
    result = await get_job_status(job_id)
    return JobStatusResponse(**result)


@router.post("/{path}", response_model=AsyncProcessResponse)
async def process_dynamic_webhook(
    path: str,
    request: ProcessRequest,
    authorization: str = Header(None),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """
    Process an incoming webhook using dynamic paths configured in WebhookConfig.
    Validates token and publishes to RabbitMQ via `rabbitmq_client`.
    """
    # Find webhook config
    query = select(WebhookConfig).where(WebhookConfig.path == path, WebhookConfig.is_active == True)
    result = await db.execute(query)
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(status_code=404, detail="Webhook path not found or inactive")
        
    # Check Auth
    if config.require_token:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
        token = authorization.replace("Bearer ", "")
        if token != config.access_token:
            raise HTTPException(status_code=403, detail="Invalid token")
            
    # Set target agent
    target_agent_id = str(config.target_agent_id) if config.target_agent_id else request.agent_id
    
    # Store message in history first to ensure sync
    await redis.add_message(
        session_id=request.session_id,
        role="user",
        content=request.message
    )
    
    job_id = f"job_{uuid.uuid4().hex}"
    
    # Init tracking status in Redis
    import json
    await redis.set(
        f"job:{job_id}",
        json.dumps({
            "job_id": job_id,
            "status": "queued",
            "result": None
        }),
        expire=3600
    )
    
    # Prepare payload
    payload = request.model_dump()
    payload["agent_id"] = target_agent_id
    payload["callback_url"] = request.callback_url
    
    # Publish to RabbitMQ
    success = await rabbitmq_client.publish_webhook_job(
        payload=payload,
        config_id=str(config.id),
        session_id=request.session_id,
        job_id=job_id
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to enqueue webhook job")
        
    return AsyncProcessResponse(
        job_id=job_id,
        status="queued",
        message="Webhook received and queued for processing"
    )
