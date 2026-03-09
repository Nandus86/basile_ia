"""
RabbitMQ Consumer Worker for Webhook Processing
"""
import asyncio
import json
import logging
import aio_pika

from app.services.rabbitmq_service import rabbitmq_client
from app.database import async_session_maker
from app.orchestrator import run_orchestrator_v2
from app.redis_client import redis_client

logger = logging.getLogger(__name__)


async def process_webhook_message(message: aio_pika.IncomingMessage):
    """Callback to process a message from RabbitMQ"""
    async with message.process():
        try:
            body = json.loads(message.body.decode())
            payload = body.get("payload", {})
            config_id = body.get("webhook_config_id")
            session_id = body.get("session_id")
            job_id = body.get("job_id")

            logger.info(f"Processing webhook job {job_id} for session {session_id}")

            # Prepare args for orchestrator
            message_text = payload.get("message")
            agent_id = payload.get("agent_id")
            user_access_level = payload.get("user_access_level", "normal")
            context_data = payload.get("context_data")
            transition_data = payload.get("transition_data")
            callback_url = payload.get("callback_url")
            
            # Set to in_progress
            await redis_client.set(
                f"job:{job_id}",
                json.dumps({
                    "job_id": job_id,
                    "status": "in_progress",
                    "result": None
                }),
                expire=3600
            )

            try:
                from sqlalchemy.future import select
                from app.models.job_log import JobLog
                async with async_session_maker() as db_session:
                    query = select(JobLog).where(JobLog.job_id == job_id)
                    res = await db_session.execute(query)
                    job_log = res.scalar_one_or_none()
                    if job_log:
                        job_log.status = "in_progress"
                        await db_session.commit()
            except Exception as e:
                logger.error(f"Failed to update JobLog in_progress: {e}")

            async with async_session_maker() as db:
                from app.orchestrator.agent_factory import AgentFactory
                from langchain_core.messages import HumanMessage, AIMessage

                # Check if target agent exists and has output schema
                agent_config = None
                agent = None
                logger.info(f"[Consumer] agent_id={agent_id}, session={session_id}")
                
                factory = AgentFactory(db)
                if agent_id:
                    agent = await factory.get_agent_by_id(agent_id)
                    logger.info(f"[Consumer] Agent found: {agent.name if agent else 'None'}, has output_schema: {bool(agent.output_schema) if agent else False}")
                    
                    if agent:
                        # Auto-map extra root fields from payload to context or transition data
                        standard_keys = {"message", "session_id", "agent_id", "user_access_level", "metadata", "context_data", "transition_data", "callback_url", "source", "event_type", "sender_id", "sender_name", "timestamp"}
                        ctx_keys = set(agent.input_schema.keys()) if agent.input_schema else set()
                        trans_keys = set(agent.transition_input_schema.keys()) if agent.transition_input_schema else set()
                        
                        c_data = context_data or {}
                        t_data = transition_data or {}
                        
                        for k, v in payload.items():
                            if k in standard_keys: continue
                            if k in ctx_keys:
                                c_data[k] = v
                            else:
                                t_data[k] = v
                                
                        if c_data: context_data = c_data
                        if t_data: transition_data = t_data

                    if agent and agent.output_schema:
                        agent_config = await factory.get_agent_config(agent)
                        logger.info(f"[Consumer] Using STRUCTURED mode with schema keys: {list(agent.output_schema.keys())}")
                else:
                    logger.warning(f"[Consumer] No agent_id provided, falling back to standard orchestrator")

                # Resolve STM configuration
                stm_enabled = True
                stm_ttl_seconds = 86400
                if agent and agent.config:
                    stm_enabled = agent.config.get("short_term_memory_enabled", True)
                    stm_ttl_hours = agent.config.get("short_term_memory_ttl_hours", 24)
                    stm_ttl_seconds = int(stm_ttl_hours * 3600)
                    
                # Get history
                history = []
                if stm_enabled:
                    history = await redis_client.get_conversation(session_id)

                # Configure resilience
                max_retries = 3
                retry_delay = 1.0
                if agent_config and "resilience" in agent_config:
                    res = agent_config.get("resilience", {})
                    max_retries = res.get("max_retries", 3)
                    retry_delay = res.get("retry_delay_seconds", 1.0)
                
                attempts = 0
                last_exception = None
                
                while attempts <= max_retries:
                    attempts += 1
                    try:
                        if agent_config:
                            # Run Structured Agent
                            messages = []
                            for msg in history:
                                if msg.get("role") == "user":
                                    messages.append(HumanMessage(content=msg["content"]))
                                elif msg.get("role") == "assistant":
                                    messages.append(AIMessage(content=msg["content"]))
                            messages.append(HumanMessage(content=message_text))

                            rag_context = None
                            try:
                                from app.services.rag_service import get_rag_context
                                rag_context = await get_rag_context(db, agent_config["id"], message_text, limit=5)
                            except Exception:
                                pass

                            # Information Bases Retrieval for structured agents
                            try:
                                from app.models.agent import Agent as AgentModel
                                from sqlalchemy import select as sa_select
                                from sqlalchemy.orm import selectinload
                                from app.weaviate_client import get_weaviate
                                
                                ib_result = await db.execute(
                                    sa_select(AgentModel).options(selectinload(AgentModel.information_bases)).where(AgentModel.id == agent_id)
                                )
                                ib_agent = ib_result.scalar_one_or_none()
                                if ib_agent and ib_agent.information_bases:
                                    base_codes = [b.code for b in ib_agent.information_bases if b.is_active]
                                    if base_codes:
                                        # Collect possible user IDs from context_data values
                                        possible_ids = []
                                        ctx = context_data or {}
                                        for v in ctx.values():
                                            if isinstance(v, str) and v.strip():
                                                possible_ids.append(v.strip())
                                        if session_id:
                                            possible_ids.append(str(session_id))
                                        
                                        weaviate_client = get_weaviate()
                                        if weaviate_client and possible_ids:
                                            all_info_nodes = []
                                            for uid in possible_ids:
                                                info_nodes = await weaviate_client.search_information_bases(
                                                    base_codes=base_codes,
                                                    user_id=uid,
                                                    query=message_text,
                                                    limit=5
                                                )
                                                if info_nodes:
                                                    all_info_nodes.extend(info_nodes)
                                            if all_info_nodes:
                                                seen = set()
                                                unique_nodes = []
                                                for n in all_info_nodes:
                                                    if n['content'] not in seen:
                                                        seen.add(n['content'])
                                                        unique_nodes.append(n)
                                                logger.info(f"[Consumer] 📚 Retrieved {len(unique_nodes)} Information Base contexts")
                                                info_str = "\n".join([f"- {n['content']} (Meta: {n['metadata']})" for n in unique_nodes[:10]])
                                                agent_config["system_prompt"] = agent_config.get("system_prompt", "") + f"\n\n## Contextualização Personalizada Externa\n\nInformações anexadas aos bancos de dados do usuário logado:\n{info_str}\n"
                            except Exception as ib_err:
                                logger.error(f"[Consumer] Failed to retrieve Information Bases: {ib_err}")

                            result_dict = await factory.invoke_agent_structured(
                                agent_config=agent_config,
                                messages=messages,
                                rag_context=rag_context,
                                context_data=context_data
                            )
                            
                            logger.info(f"[Consumer] Structured result keys: {list(result_dict.keys()) if isinstance(result_dict, dict) else 'NOT_DICT'}")
                            
                            # Store serialized dictionary response
                            response_text = result_dict if isinstance(result_dict, dict) else result_dict.get("output", str(result_dict))
                            
                            if stm_enabled:
                                await redis_client.add_message(
                                    session_id=session_id,
                                    role="assistant",
                                    content=str(response_text),
                                    ttl_seconds=stm_ttl_seconds
                                )
                            final_result = response_text
                            agent_used = agent_config["name"]
                        
                        else:
                            # Run Standard Orchestrator V2 (No custom output schema or agent not specified)
                            logger.info(f"[Consumer] Using STANDARD mode (no output_schema)")
                            result = await run_orchestrator_v2(
                                message=message_text,
                                session_id=session_id,
                                history=history,
                                agent_id=agent_id,
                                db=db,
                                user_access_level=user_access_level,
                                context_data=context_data
                            )

                            if stm_enabled:
                                await redis_client.add_message(
                                    session_id=session_id,
                                    role="assistant",
                                    content=result["response"],
                                    ttl_seconds=stm_ttl_seconds
                                )
                            final_result = result["response"]
                            agent_used = result.get("agent_used")
                        
                        # If execution succeeded, break retry loop
                        break

                    except Exception as e:
                        last_exception = e
                        logger.error(f"[Consumer] Attempt {attempts}/{max_retries+1} failed: {str(e)}")
                        if attempts <= max_retries:
                            import asyncio
                            logger.info(f"[Consumer] Retrying in {retry_delay} seconds...")
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                        else:
                            logger.error(f"[Consumer] All {max_retries+1} attempts failed for job {job_id}.")
                            raise last_exception
                
            # Set to completed
            job_data = {
                "job_id": job_id,
                "status": "completed",
                "result": final_result,
                "agent_used": agent_used
            }
            if transition_data:
                job_data["transition_data"] = transition_data

            await redis_client.set(
                f"job:{job_id}",
                json.dumps(job_data),
                expire=3600
            )

            try:
                from sqlalchemy.future import select
                from app.models.job_log import JobLog
                from datetime import datetime, timezone
                async with async_session_maker() as db_session:
                    query = select(JobLog).where(JobLog.job_id == job_id)
                    res = await db_session.execute(query)
                    job_log = res.scalar_one_or_none()
                    if job_log:
                        job_log.status = "completed"
                        job_log.response_data = final_result if isinstance(final_result, dict) else {"output": final_result}
                        job_log.completed_at = datetime.now(timezone.utc)
                        if job_log.created_at:
                            job_log.duration_ms = int((job_log.completed_at - job_log.created_at).total_seconds() * 1000)
                        await db_session.commit()
            except Exception as e:
                logger.error(f"Failed to update JobLog completed: {e}")

            logger.info(f"Successfully processed webhook job {job_id}, result type: {type(final_result).__name__}")

            if callback_url:
                import httpx
                try:
                    async with httpx.AsyncClient() as client:
                        response_data = {
                            "status": "completed",
                            "job_id": job_id,
                            "result": final_result,
                            "agent_used": agent_used
                        }
                        
                        if transition_data:
                            response_data["transition_data"] = transition_data
                            
                        await client.post(callback_url, json=response_data, timeout=10.0)
                        logger.info(f"Callback sent to {callback_url}")
                except Exception as cb_err:
                    logger.error(f"Failed to send callback to {callback_url}: {str(cb_err)}")

        except Exception as e:
            logger.error(f"Error processing webhook job from RabbitMQ: {str(e)}")
            job_id = body.get("job_id") if 'body' in locals() else None
            if job_id:
                try:
                    await redis_client.set(
                        f"job:{job_id}",
                        json.dumps({
                            "job_id": job_id,
                            "status": "failed",
                            "error": str(e)
                        }),
                        expire=3600
                    )
                    from sqlalchemy.future import select
                    from app.models.job_log import JobLog
                    from datetime import datetime, timezone
                    async with async_session_maker() as db_session:
                        query = select(JobLog).where(JobLog.job_id == job_id)
                        res = await db_session.execute(query)
                        job_log = res.scalar_one_or_none()
                        if job_log:
                            job_log.status = "failed"
                            job_log.error_message = str(e)
                            job_log.completed_at = datetime.now(timezone.utc)
                            if job_log.created_at:
                                job_log.duration_ms = int((job_log.completed_at - job_log.created_at).total_seconds() * 1000)
                            await db_session.commit()
                except Exception:
                    pass


async def start_rabbitmq_consumer():
    """Start listening to the webhook queue"""
    if not rabbitmq_client.channel:
        logger.error("RabbitMQ channel not available for consumer")
        return

    try:
        queue = await rabbitmq_client.channel.get_queue(rabbitmq_client.webhook_queue_name)
        await queue.consume(process_webhook_message)
        logger.info("RabbitMQ Consumer started listening for webhooks")
    except Exception as e:
        logger.error(f"Failed to start RabbitMQ consumer: {str(e)}")
