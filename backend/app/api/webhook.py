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
    AsyncProcessResponse, JobStatusResponse,
    ChatFeedbackRequest, ChatFeedbackResponse
)
from app.orchestrator import run_orchestrator_v2
from app.models.job_log import JobLog

import httpx
import json
import asyncio
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from app.config import settings

router = APIRouter()

def _extract_search_fields(payload: dict) -> dict:
    """Extract denormalized search fields from a request payload for indexed queries."""
    if not isinstance(payload, dict):
        return {}
    church = payload.get("church") or {}
    member = payload.get("member") or {}
    context_data = payload.get("context_data") or {}
    return {
        "session_id": payload.get("session_id"),
        "church_name": church.get("church_name"),
        "member_name": (
            member.get("fullname")
            or context_data.get("name")
            or payload.get("name")
        ),
        "user_message": payload.get("message"),
    }

def _extract_agent_response(response_data: dict) -> str:
    """Extract agent response text from response_data dict."""
    if not isinstance(response_data, dict):
        return None
    resp = (
        response_data.get("result")
        or response_data.get("response")
        or response_data.get("output")
        or response_data.get("resposta")
    )
    if isinstance(resp, dict):
        resp = resp.get("result") or resp.get("output") or resp.get("response") or str(resp)
    return resp if isinstance(resp, str) else None

@router.post("/trigger/personalizado/{path:path}")
async def proxy_disparador_trigger(path: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
        
    disparador_url = f"{settings.DISPARADOR_SERVICE_URL}/webhook/trigger/personalizado/{path}"
    
    x_api_key = request.headers.get("X-API-Key")
    forward_headers = {}
    if x_api_key:
        forward_headers["X-API-Key"] = x_api_key
        
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(disparador_url, json=body, headers=forward_headers)
            try:
                content = resp.json()
            except ValueError:
                content = {"detail": "Proxy received an invalid JSON response from the Disparador service. This usually means a DB connection error or unexpected crash in the container.", "raw_error": resp.text}
            
            return JSONResponse(status_code=resp.status_code, content=content)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Erro ao contatar o microserviço Disparador: {e}")

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
    # We combine model_dump() with model_extra (extra fields like system, member)
    from app.context import set_request_context
    full_payload = {**request.model_dump(), **(request.model_extra or {})}
    print(f"[Webhook] 📥 Received full request context: {list(full_payload.keys())}")
    set_request_context(full_payload)
    
    # Extract extra root fields and add to context_data
    # This ensures that fields like "church", "member", "system" are passed to the agent's context_data
    standard_keys = {"message", "session_id", "agent_id", "user_access_level", "metadata", "context_data", "transition_data", "callback_url"}
    c_data = request.context_data or {}
    for k, v in full_payload.items():
        if k not in standard_keys:
            c_data[k] = v
    if c_data:
        request.context_data = c_data
        
    try:
        from app.worker.tasks import process_message_task
        import uuid
        from app.models.job_log import JobLog
        
        # Log to DB
        _payload = request.model_dump()
        job_log = JobLog(
            job_id=f"sync_{uuid.uuid4().hex}",
            webhook_path="/process",
            status="in_progress",
            request_data=_payload,
            callback_url=request.callback_url,
            **_extract_search_fields(_payload)
        )
        db.add(job_log)
        await db.commit()
        await db.refresh(job_log)
        
        # Call the worker's Agent-First task directly
        # process_message_task returns the full response dictionary, handles MTM history, and executes the agent directly.
        task_result = await process_message_task(
            ctx={},  # worker job context not needed for sync run
            message=request.message,
            session_id=request.session_id,
            agent_id=request.agent_id,
            user_access_level=request.user_access_level,
            context_data=request.context_data,
            transition_data=request.transition_data,
            callback_url=request.callback_url
        )
        
        processing_time = (time.time() - start_time) * 1000
        
        # Update JobLog with success - salvar payload completo (mesmo que vai para o callback)
        job_log.status = "completed"
        task_response = task_result.get("response", "")
        # Se response for dict, extrair output ou response; senão usar como string
        if isinstance(task_response, dict):
            result_str = task_response.get("output", task_response.get("response", str(task_response)))
        else:
            result_str = task_response
        full_response_data = {
            "status": "completed",
            "job_id": job_log.job_id,
            "result": result_str,
            "agent_used": task_result.get("agent_used")
        }
        transition_data = task_result.get("transition_data")
        if transition_data:
            full_response_data["transition_data"] = transition_data
        job_log.response_data = full_response_data
        job_log.agent_response = _extract_agent_response(full_response_data)
        job_log.duration_ms = int(processing_time)
        
        try:
            from datetime import datetime, timezone
            job_log.completed_at = datetime.now(timezone.utc)
            await db.commit()
        except Exception:
            pass

        return ProcessResponse(
            response=task_result.get("response", ""),
            agent_used=task_result.get("agent_used"),
            processing_time_ms=processing_time,
            transition_data=task_result.get("transition_data"),
            last_agent=task_result.get("last_agent")
        )
        
    except Exception as e:
        processing_time = (time.time() - start_time) * 1000
        if 'job_log' in locals():
            try:
                from datetime import datetime, timezone
                job_log.status = "failed"
                job_log.error_message = str(e)
                job_log.duration_ms = int(processing_time)
                job_log.completed_at = datetime.now(timezone.utc)
                await db.commit()
            except:
                pass
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
    
    # ═══════════════════════════════════════════════════════
    # ACTIVE WORKFLOW RUN CHECK (Human-in-the-loop Resume)
    # ═══════════════════════════════════════════════════════
    if request.session_id:
        active_wf_run = await redis.get(f"active_workflow_run:{request.session_id}")
        if active_wf_run:
            from app.worker.tasks import process_message_task
            task_result = await process_message_task(
                ctx={},
                message=request.message,
                session_id=request.session_id,
                agent_id=request.agent_id,
                user_access_level=request.user_access_level,
                context_data=request.context_data,
                transition_data=request.transition_data,
                callback_url=None
            )
            return {
                "output": task_result.get("response", ""),
                "agent_used": task_result.get("agent_used"),
                "processing_time_ms": (time.time() - start_time) * 1000
            }
    
    # Set request context for deep services (MCP tools)
    from app.context import set_request_context
    full_payload = {**request.model_dump(), **(request.model_extra or {})}
    set_request_context(full_payload)
    
    # Auto-map extra root fields to context_data
    standard_keys = {"message", "session_id", "agent_id", "user_access_level", "metadata", "context_data", "transition_data", "callback_url"}
    c_data = request.context_data or {}
    for k, v in full_payload.items():
        if k not in standard_keys:
            c_data[k] = v
    if request.session_id and "session_id" not in c_data:
        c_data["session_id"] = request.session_id
    request.context_data = c_data
    
    try:
        # Initialize factory and resolve STM
        factory = AgentFactory(db)
        
        # Get agent
        if request.agent_id:
            agent = await factory.get_agent_by_id(request.agent_id)
        else:
            agents = await factory.get_accessible_agents(request.user_access_level)
            agent = agents[0] if agents else None
            
        stm_enabled = True
        stm_ttl_seconds = 86400
        if agent and agent.config:
            global_memory_enabled = agent.config.get("memory_enabled", True)
            stm_enabled = agent.config.get("short_term_memory_enabled", True) and global_memory_enabled
            stm_ttl_hours = agent.config.get("short_term_memory_ttl_hours", 24)
            stm_ttl_seconds = int(stm_ttl_hours * 3600)
            
        # Get conversation history
        history = []
        if stm_enabled:
            history = await redis.get_conversation(request.session_id)
            
            # Add current message to history
            await redis.add_message(
                session_id=request.session_id,
                role="user",
                content=request.message,
                ttl_seconds=stm_ttl_seconds
            )
        
        _payload_s = request.model_dump()
        job_log = JobLog(
            job_id=f"sync_{uuid.uuid4().hex}",
            webhook_path="/process/structured",
            status="in_progress",
            request_data=_payload_s,
            **_extract_search_fields(_payload_s)
        )
        db.add(job_log)
        await db.commit()
        await db.refresh(job_log)
        
        if not agent:
            processing_time = (time.time() - start_time) * 1000
            return {
                "output": "Nenhum agente disponível.",
                "agent_used": None,
                "processing_time_ms": processing_time
            }
        
        # Get agent config
        agent_config = await factory.get_agent_config(agent, context_data=request.context_data)
        
        # Build messages
        messages = []
        for msg in history:
            if msg.get("role") == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg.get("role") == "assistant":
                messages.append(AIMessage(content=msg["content"]))
        messages.append(HumanMessage(content=request.message))
        
        # Enrich agent prompt and load collaborator tools, memory, and information bases
        from app.worker.tasks import (
            _build_information_base_tools,
            _enrich_agent_prompt,
            _check_trigger_mcps
        )

        # Load session context for continuity
        session_context = None
        try:
            session_context = await redis.get_session_context(request.session_id)
        except Exception as e:
            print(f"[Structured] ⚠️ Failed to load session context: {e}")

        # [INFORMATION BASE TOOLS] Build IB tools first to know if RAG enrichment should skip
        has_ib_tools = False
        try:
            ib_tools = await _build_information_base_tools(db, str(agent.id), request.context_data)
            if ib_tools:
                existing_tools = agent_config.get("tools", []) or []
                agent_config["tools"] = existing_tools + ib_tools
                agent_config["has_tools"] = True
                has_ib_tools = True
                print(f"[Structured] 🔍 Added {len(ib_tools)} information base tools")
        except Exception as e:
            print(f"[Structured] ❌ Error loading information base tools: {e}")

        # Enrich prompt (RAG, InfoBases, VectorMemory, Collaborators tools, Session Continuity)
        rag_context = await _enrich_agent_prompt(
            db=db,
            agent_config=agent_config,
            agent_id=str(agent.id),
            message=request.message,
            session_id=request.session_id,
            context_data=request.context_data,
            history=history or [],
            transition_data=request.transition_data,
            session_context=session_context,
            user_access_level=request.user_access_level,
            has_ib_tools=has_ib_tools,
            history_source="STM" if history else "NONE",
        )

        # [TRIGGER MCPs] Check local trigger MCPs
        try:
            trigger_results = await _check_trigger_mcps(db, str(agent.id), request.message, request.context_data)
            if trigger_results:
                agent_config["system_prompt"] = agent_config.get("system_prompt", "") + trigger_results
                print(f"[Structured] 🎯 Trigger MCP results injected")
        except Exception as e:
            print(f"[Structured] ❌ Error checking trigger MCPs: {e}")

        # Adicionar regra de encerramento de interação
        agent_config["system_prompt"] = agent_config.get("system_prompt", "") + (
            "\n\n## Regra de Encerramento Subentendido\n"
            "Caso a mensagem atual do usuário seja EXCLUSIVAMENTE um agradecimento final, despedida ou negação de mais ajuda (ex: 'não, era só isso, obrigado', 'tchau', 'valeu'), "
            "e NÃO contenha nenhuma nova solicitação, você DEVE responder EXATAMENTE E APENAS com o código: `[FIM_DE_INTERACAO]`."
        )

        # Reforçar a regra de metadados temporais
        agent_config["system_prompt"] = agent_config.get("system_prompt", "") + (
            "\n\n## Atenção aos Metadados Temporais\n"
            "As mensagens no histórico contêm o prefixo `[CONTEXTO_TEMPORAL: ...]`. "
            "Este prefixo NÃO faz parte do conteúdo da mensagem e NUNCA deve ser incluído na sua resposta."
        )
        
        # Invoke with structured output
        result = await factory.invoke_agent_structured(
            agent_config=agent_config,
            messages=messages,
            rag_context=rag_context,
            context_data=request.context_data
        )
        
        # Store response in history
        output_text = result.get("output", str(result))
        if stm_enabled:
            await redis.add_message(
                session_id=request.session_id,
                role="assistant",
                content=output_text,
                ttl_seconds=stm_ttl_seconds
            )
        
        processing_time = (time.time() - start_time) * 1000
        
        job_log.status = "completed"
        _resp_s = {**result, "agent_used": agent_config["name"]}
        job_log.response_data = _resp_s
        job_log.agent_response = _extract_agent_response(_resp_s)
        job_log.duration_ms = int(processing_time)
        from datetime import datetime, timezone
        job_log.completed_at = datetime.now(timezone.utc)
        await db.commit()

        # Return structured response with metadata
        response_dict = {
            **result,
            "agent_used": agent_config["name"],
            "processing_time_ms": processing_time
        }
        
        if request.transition_data is not None:
            response_dict["transition_data"] = request.transition_data
            
        return response_dict
        
    except Exception as e:
        processing_time = (time.time() - start_time) * 1000
        from app.worker.tasks import _invoke_recovery_agent
        friendly_message = await _invoke_recovery_agent(request.message, str(e))
        
        try:
            await redis.add_message(
                session_id=request.session_id, role="assistant",
                content=friendly_message, ttl_seconds=86400
            )
        except Exception:
            pass
            
        return {
            "output": friendly_message,
            "error": str(e),
            "agent_used": "Agente de Recuperação",
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
        from app.database import async_session_maker
        import uuid
        
        # Generate an early job_id or use one passed from enqueue
        job_id = f"job_{uuid.uuid4().hex}"
        
        # Auto-map extra root fields to context_data
        standard_keys = {"message", "session_id", "agent_id", "user_access_level", "metadata", "context_data", "transition_data", "callback_url"}
        full_payload = {**request.model_dump(), **(request.model_extra or {})}
        c_data = request.context_data or {}
        for k, v in full_payload.items():
            if k not in standard_keys:
                c_data[k] = v
        if c_data:
            request.context_data = c_data
        
        async with async_session_maker() as db_session:
            _payload_a = request.model_dump()
            job_log = JobLog(
                job_id=job_id,
                webhook_path="/process/async",
                status="queued",
                request_data=_payload_a,
                **_extract_search_fields(_payload_a)
            )
            db_session.add(job_log)
            await db_session.commit()

        queued_job_id = await enqueue_process_message(
            message=request.message,
            session_id=request.session_id,
            agent_id=request.agent_id,
            user_access_level=request.user_access_level,
            context_data=request.context_data,
            transition_data=request.transition_data,
            callback_url=request.callback_url,
            job_id=job_id # Passing to use our custom uuid
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
        from app.database import async_session_maker
        import uuid
        
        job_id = f"job_{uuid.uuid4().hex}"
        
        # Auto-map extra root fields to context_data
        standard_keys = {"message", "session_id", "agent_id", "user_access_level", "metadata", "context_data", "transition_data", "callback_url"}
        full_payload = {**request.model_dump(), **(request.model_extra or {})}
        c_data = request.context_data or {}
        for k, v in full_payload.items():
            if k not in standard_keys:
                c_data[k] = v
        if c_data:
            request.context_data = c_data
        async with async_session_maker() as db_session:
            _payload_sa = request.model_dump()
            job_log = JobLog(
                job_id=job_id,
                webhook_path="/process/structured/async",
                status="queued",
                request_data=_payload_sa,
                **_extract_search_fields(_payload_sa)
            )
            db_session.add(job_log)
            await db_session.commit()

        queued_job_id = await enqueue_process_structured(
            message=request.message,
            session_id=request.session_id,
            agent_id=request.agent_id,
            user_access_level=request.user_access_level,
            context_data=request.context_data,
            transition_data=request.transition_data,
            callback_url=request.callback_url,
            job_id=job_id
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


@router.post("/feedback", response_model=ChatFeedbackResponse)
async def submit_chat_feedback(
    request: ChatFeedbackRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Submete um feedback (RLHF) de uma resposta do agente.
    Usa LLM para sintetizar uma regra e a salva no Weaviate.
    """
    from app.services.vector_memory_service import extract_training_feedback
    
    try:
        rule_extracted = await extract_training_feedback(
            agent_id=request.agent_id,
            feedback_type=request.feedback_type,
            user_message=request.user_message,
            agent_response=request.agent_response,
            correction_note=request.correction_note
        )
        
        if rule_extracted:
            return ChatFeedbackResponse(
                success=True,
                message="Feedback recebido e regra de treinamento gravada com sucesso.",
                rule_extracted=rule_extracted
            )
        else:
            return ChatFeedbackResponse(
                success=True,
                message="Feedback recebido, mas nenhuma regra específica pôde ser extraída.",
                rule_extracted=None
            )
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/process/stream")
async def process_message_stream(
    request: ProcessRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """
    Process a message with SSE streaming for real-time feedback.
    """
    from app.orchestrator.supervisor import run_supervisor_stream
    from app.utils.timezone import resolve_timezone_name
    from starlette.responses import StreamingResponse
    import json
    import asyncio
    
    async def event_generator():
        try:
            # Prepare data (similar to process_message)
            message = request.message
            session_id = request.session_id
            agent_id = request.agent_id
            user_access_level = request.user_access_level
            
            # Auto-map extra root fields to context_data
            standard_keys = {"message", "session_id", "agent_id", "user_access_level", "metadata", "context_data", "transition_data", "callback_url"}
            full_payload = {**request.model_dump(), **(request.model_extra or {})}
            c_data = request.context_data or {}
            for k, v in full_payload.items():
                if k not in standard_keys:
                    c_data[k] = v
            if request.session_id and "session_id" not in c_data:
                c_data["session_id"] = request.session_id
            request.context_data = c_data
                
            context_data = request.context_data or {}
            transition_data = request.transition_data or {}
            
            # Load history
            history = await redis.get_conversation(session_id)
            
            # Resolve Timezone
            tz_name = "America/Sao_Paulo"
            if transition_data:
                 tz_name = resolve_timezone_name(transition_data)

            # Convert history to LangChain messages
            from langchain_core.messages import HumanMessage, AIMessage
            lc_messages = []
            for msg in (history or []):
                if msg.get("role") == "user":
                    lc_messages.append(HumanMessage(content=msg.get("content", "")))
                elif msg.get("role") == "assistant":
                    lc_messages.append(AIMessage(content=msg.get("content", "")))
            
            # Add current message
            lc_messages.append(HumanMessage(content=message))

            # Record user message in STM
            await redis.add_message(
                session_id=session_id,
                role="user",
                content=message,
                tz_name=tz_name
            )

            # Start streaming
            if agent_id:
                from app.orchestrator.agent_factory import AgentFactory
                factory = AgentFactory(db)
                agent_obj = await factory.get_agent_by_id(agent_id)
                if not agent_obj:
                    yield f"data: {json.dumps({'type': 'error', 'data': f'Agente {agent_id} não encontrado.'}, ensure_ascii=False)}\n\n"
                    return
                    
                agent_config = await factory.get_agent_config(agent_obj, context_data=context_data)
                
                # Check for bypass mode (similar to production)
                if agent_config.get("bypass_llm", False):
                     wf_result = None
                     try:
                         from app.services.workflow_engine import WorkflowEngine
                         from sqlalchemy.orm import selectinload
                         from sqlalchemy import select as sa_select
                         from app.models.agent import Agent as AgentModel
                         
                         agent_obj_result = await db.execute(
                             sa_select(AgentModel)
                             .options(selectinload(AgentModel.workflows))
                             .where(AgentModel.id == agent_id)
                         )
                         agent_with_wf = agent_obj_result.scalar_one_or_none()
                         
                         if agent_with_wf and agent_with_wf.workflows:
                             active_workflows = [w for w in agent_with_wf.workflows if w.is_active]
                             if active_workflows:
                                 wf = active_workflows[0]
                                 engine = WorkflowEngine(db)
                                 trigger_data = (context_data or {}).copy()
                                 trigger_data["message"] = message
                                 trigger_data["session_id"] = session_id
                                 
                                 result_ctx = await engine.execute(
                                     workflow_id=wf.id,
                                     trigger_data=trigger_data,
                                     trigger_type="bypass_auto_trigger",
                                 )
                                 
                                 wf_result = result_ctx.get('result')
                                 if isinstance(wf_result, dict):
                                     if "result" in wf_result:
                                         wf_result = wf_result["result"]
                                     elif "saida" in wf_result:
                                         saida_val = wf_result["saida"]
                                         if isinstance(saida_val, dict) and "result" in saida_val:
                                             wf_result = saida_val["result"]
                                         else:
                                             wf_result = saida_val

                                 if wf_result is not None:
                                     if isinstance(wf_result, (dict, list)):
                                         wf_result = json.dumps(wf_result, ensure_ascii=False, indent=2)
                                     else:
                                         wf_result = str(wf_result)
                                 else:
                                     wf_result = f"Automação '{wf.name}' executada com sucesso."
                     except Exception as e:
                         print(f"[Stream] ❌ Error executing workflow during bypass: {e}")
                         wf_result = f"Erro na automação: {str(e)}"
                     
                     output_text = wf_result if wf_result is not None else message
                     yield f"data: {json.dumps({'type': 'chunk', 'data': output_text}, ensure_ascii=False)}\n\n"
                     yield f"data: {json.dumps({'type': 'final', 'data': 'completed'}, ensure_ascii=False)}\n\n"
                     return

                # Enrich agent prompt and load collaborator tools, memory, and information bases
                from app.worker.tasks import (
                    _build_information_base_tools,
                    _enrich_agent_prompt,
                    _check_trigger_mcps
                )

                # Load session context for continuity
                session_context = None
                try:
                    session_context = await redis.get_session_context(session_id)
                except Exception as e:
                    print(f"[Stream] ⚠️ Failed to load session context: {e}")

                # [INFORMATION BASE TOOLS] Build IB tools first to know if RAG enrichment should skip
                has_ib_tools = False
                try:
                    ib_tools = await _build_information_base_tools(db, agent_id, context_data)
                    if ib_tools:
                        existing_tools = agent_config.get("tools", []) or []
                        agent_config["tools"] = existing_tools + ib_tools
                        agent_config["has_tools"] = True
                        has_ib_tools = True
                        print(f"[Stream] 🔍 Added {len(ib_tools)} information base tools")
                except Exception as e:
                    print(f"[Stream] ❌ Error loading information base tools: {e}")

                # Enrich prompt (RAG, InfoBases, VectorMemory, Collaborators tools, Session Continuity)
                rag_context = await _enrich_agent_prompt(
                    db=db,
                    agent_config=agent_config,
                    agent_id=agent_id,
                    message=message,
                    session_id=session_id,
                    context_data=context_data,
                    history=history or [],
                    transition_data=transition_data,
                    session_context=session_context,
                    user_access_level=user_access_level,
                    has_ib_tools=has_ib_tools,
                    history_source="STM" if history else "NONE",
                )

                # [TRIGGER MCPs] Check local trigger MCPs
                try:
                    trigger_results = await _check_trigger_mcps(db, agent_id, message, context_data)
                    if trigger_results:
                        agent_config["system_prompt"] = agent_config.get("system_prompt", "") + trigger_results
                        print(f"[Stream] 🎯 Trigger MCP results injected")
                except Exception as e:
                    print(f"[Stream] ❌ Error checking trigger MCPs: {e}")

                # Adicionar regra de encerramento de interação
                agent_config["system_prompt"] = agent_config.get("system_prompt", "") + (
                    "\n\n## Regra de Encerramento Subentendido\n"
                    "Caso a mensagem atual do usuário seja EXCLUSIVAMENTE um agradecimento final, despedida ou negação de mais ajuda (ex: 'não, era só isso, obrigado', 'tchau', 'valeu'), "
                    "e NÃO contenha nenhuma nova solicitação, você DEVE responder EXATAMENTE E APENAS com o código: `[FIM_DE_INTERACAO]`."
                )

                # Reforçar a regra de metadados temporais
                agent_config["system_prompt"] = agent_config.get("system_prompt", "") + (
                    "\n\n## Atenção aos Metadados Temporais\n"
                    "As mensagens no histórico contêm o prefixo `[CONTEXTO_TEMPORAL: ...]`. "
                    "Este prefixo NÃO faz parte do conteúdo da mensagem e NUNCA deve ser incluído na sua resposta."
                )

                async for event in factory.invoke_agent_stream(
                    agent_config=agent_config,
                    messages=lc_messages,
                    context_data=context_data
                ):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.01)
                    await asyncio.sleep(0.01)
            else:
                async for event in run_supervisor_stream(
                    message=message,
                    session_id=session_id,
                    history=history, # run_supervisor_stream takes history as dict list and converts it inside if needed, wait.
                    agent_id=None,
                    db=db,
                    user_access_level=user_access_level,
                    context_data=context_data
                ):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.01)
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(), 
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"}
    )


from typing import Union

@router.post("/{path}", response_model=Union[AsyncProcessResponse, ProcessResponse])
async def process_dynamic_webhook(
    path: str,
    request: ProcessRequest,
    authorization: str = Header(None),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """
    Process an incoming webhook using dynamic paths configured in WebhookConfig.
    Validates token and handles synchronously or publishes to RabbitMQ via `rabbitmq_client` based on sync_mode.
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
            
    # Resolve target agent
    target_agent_id = str(config.target_agent_id) if config.target_agent_id else request.agent_id
    
    if getattr(config, "sync_mode", False):
        # SYNCHRONOUS MODE
        from app.worker.tasks import process_message_task
        
        # Auto-map extra root fields to context
        standard_keys = {"message", "session_id", "agent_id", "user_access_level", "metadata", "context_data", "transition_data", "callback_url"}
        payload_data = request.model_dump()
        c_data = request.context_data or {}
        for k, v in payload_data.items():
            if k not in standard_keys:
                c_data[k] = v
        if c_data:
            request.context_data = c_data
            
        start_time = time.time()
        _payload_dyn = request.model_dump()
        job_log = JobLog(
            job_id=f"sync_{uuid.uuid4().hex}",
            webhook_path=path,
            status="in_progress",
            request_data=_payload_dyn,
            **_extract_search_fields(_payload_dyn)
        )
        db.add(job_log)
        await db.commit()
        await db.refresh(job_log)
        
        # Set request context for deep services (MCP tools)
        from app.context import set_request_context
        set_request_context({**request.model_dump(), **(request.model_extra or {})})
        
        try:
            result = await process_message_task(
                ctx={},
                message=request.message,
                session_id=request.session_id,
                agent_id=target_agent_id,
                user_access_level=request.user_access_level,
                context_data=request.context_data,
                transition_data=request.transition_data,
                callback_url=None
            )
            
            processing_time = (time.time() - start_time) * 1000
            job_log.status = "completed"
            job_log.response_data = result
            job_log.agent_response = _extract_agent_response(result)
            job_log.duration_ms = int(processing_time)
            
            from datetime import datetime, timezone
            job_log.completed_at = datetime.now(timezone.utc)
            await db.commit()
            
            return ProcessResponse(
                response=result.get("response", ""),
                agent_used=result.get("agent_used", target_agent_id),
                processing_time_ms=processing_time,
                transition_data=result.get("transition_data"),
                last_agent=result.get("last_agent")
            )
        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            job_log.status = "failed"
            job_log.error_message = str(e)
            job_log.duration_ms = int(processing_time)
            from datetime import datetime, timezone
            job_log.completed_at = datetime.now(timezone.utc)
            await db.commit()
            
            from app.worker.tasks import _invoke_recovery_agent
            friendly_message = await _invoke_recovery_agent(request.message, str(e))
            
            return ProcessResponse(
                response=friendly_message,
                agent_used="Agente de Recuperação",
                processing_time_ms=processing_time,
                transition_data=None,
                last_agent="Agente de Recuperação"
            )
    
    else:
        # ASYNCHRONOUS MODE (RabbitMQ/Queue)
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
        
        job_log = JobLog(
            job_id=job_id,
            webhook_path=path,
            status="queued",
            request_data=payload,
            callback_url=request.callback_url,
            **_extract_search_fields(payload)
        )
        db.add(job_log)
        await db.commit()

        # Publish new job event to SSE channel
        try:
            from app.redis_client import redis_client as _redis
            await _redis.publish("job_updates", json.dumps({
                "event": "new_job",
                "data": {
                    "job_id": job_id,
                    "webhook_path": path,
                    "status": "queued",
                    "request_data": payload,
                    "callback_url": request.callback_url,
                    "created_at": job_log.created_at.isoformat() if job_log.created_at else None,
                }
            }))
        except Exception:
            pass

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
