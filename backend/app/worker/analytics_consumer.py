"""
RabbitMQ Consumer Worker for Analytics Agent
Consumes messages from `analytics_tasks` queue and runs the LLM processing.
"""
import asyncio
import json
import logging
import aio_pika
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from app.utils.llm_fallback import FallbackChatOpenAI as ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
import httpx

from app.services.rabbitmq_service import rabbitmq_client
from app.database import async_session_maker
from app.models.user_analytics import UserAnalytics
from app.models.conversation_message import ConversationMessage
from app.models.agent import Agent
from app.config import settings

logger = logging.getLogger(__name__)

async def process_analytics_message(message: aio_pika.abc.AbstractIncomingMessage):
    """Callback for processing analytics tasks."""
    async with message.process():
        try:
            body_str = message.body.decode('utf-8')
            payload = json.loads(body_str)
            session_id = payload.get("session_id")
            agent_id = payload.get("agent_id")
            target_date_str = payload.get("target_date")
            start_time_str = payload.get("start_time")
            end_time_str = payload.get("end_time")

            if not session_id or not agent_id:
                logger.error(f"[AnalyticsConsumer] Invalid payload: {payload}")
                return

            logger.info(f"[AnalyticsConsumer] Processing analytics for session {session_id} (target_date={target_date_str})")

            async with async_session_maker() as session:
                # Get the Agent
                import uuid as uuid_mod
                try:
                    agent_uuid = uuid_mod.UUID(str(agent_id))
                    agent_res = await session.execute(select(Agent).where(Agent.id == agent_uuid))
                except Exception:
                    agent_res = await session.execute(select(Agent).where(Agent.id == agent_id))
                agent = agent_res.scalar_one_or_none()
                if not agent:
                    logger.error(f"[AnalyticsConsumer] Agent {agent_id} not found.")
                    return
                
                # Get UserAnalytics or create on-the-fly
                user_res = await session.execute(
                    select(UserAnalytics).where(UserAnalytics.session_id == session_id)
                )
                user = user_res.scalar_one_or_none()
                if not user:
                    logger.info(f"[AnalyticsConsumer] UserAnalytics for {session_id} not found. Creating initial profile.")
                    user = UserAnalytics(
                        session_id=session_id,
                        interaction_count=payload.get("daily_msg_count") or 1,
                        engagement_score=50.0,
                        care_priority="medium",
                        profile_data={"__zona_crm": {}, "__zona_metricas": {}, "__zona_aprendizado": {}}
                    )
                    session.add(user)
                    await session.flush()

                # Fetch Config
                from app.models.analytics_config import AnalyticsConfig
                config_res = await session.execute(select(AnalyticsConfig).limit(1))
                config = config_res.scalar_one_or_none()

                # Logging to JobLogs (so it appears on UI)
                from app.models.job_log import JobLog
                job_log = JobLog(
                    id=uuid_mod.uuid4(),
                    job_id=str(uuid_mod.uuid4()),
                    webhook_path="/internal/analytics_agent",
                    status="processing",
                    request_data={"session_id": session_id, "agent": agent.name, "target_date": target_date_str}
                )
                session.add(job_log)
                await session.commit()
                
                start_time = datetime.now()

                try:
                    start_dt = None
                    end_dt = None
                    if start_time_str:
                        try:
                            start_dt = datetime.fromisoformat(start_time_str)
                        except Exception:
                            pass
                    if end_time_str:
                        try:
                            end_dt = datetime.fromisoformat(end_time_str)
                        except Exception:
                            pass

                    # Fetch messages (restricted to target day if provided)
                    msg_query = select(ConversationMessage).where(
                        ConversationMessage.session_id == session_id
                    )
                    if start_dt and end_dt:
                        msg_query = msg_query.where(
                            ConversationMessage.created_at >= start_dt,
                            ConversationMessage.created_at <= end_dt
                        )
                    elif user.last_analyzed_at:
                        msg_query = msg_query.where(ConversationMessage.created_at > user.last_analyzed_at)
                    msg_query = msg_query.order_by(ConversationMessage.created_at.asc())
                    
                    msg_res = await session.execute(msg_query)
                    raw_messages = msg_res.scalars().all()
                    
                    if not raw_messages:
                        job_log.status = "completed"
                        job_log.response_data = {"status": "no_messages_in_window"}
                        user.last_analyzed_at = datetime.now(timezone.utc)
                        await session.commit()
                        return
                    
                    # Filter messages based on allowed_endpoints if configured
                    def _is_path_allowed(msg_path: str, allowed_list: list) -> bool:
                        if not allowed_list:
                            return True
                        if not msg_path:
                            return True
                        clean_msg = msg_path.strip().strip("/").split("/")[-1].lower()
                        for item in allowed_list:
                            if not item:
                                continue
                            clean_item = item.strip().strip("/").split("/")[-1].lower()
                            if clean_item == clean_msg or clean_item in msg_path.lower():
                                return True
                        return False

                    allowed_paths = config.allowed_endpoints if (config and config.allowed_endpoints) else []
                    messages = [m for m in raw_messages if _is_path_allowed(m.webhook_path, allowed_paths)]
                    if not messages and allowed_paths:
                        # Fallback: if strict filter resulted in 0 but raw messages exist, use raw messages to avoid dropping real human interaction
                        messages = list(raw_messages)

                    # Ensure there is at least one message sent by a real user
                    user_msgs = [m for m in messages if m.role == "user"]
                    if not user_msgs:
                        job_log.status = "completed"
                        job_log.response_data = {"status": "no_user_messages_in_window"}
                        user.last_analyzed_at = datetime.now(timezone.utc)
                        await session.commit()
                        logger.info(f"[AnalyticsConsumer] Skipping LLM for {user.session_id}: no user messages found in window")
                        return

                    # Format history
                    history_text = "\n".join([f"[{m.created_at.strftime('%H:%M:%S')}] {m.role.upper()}: {m.content}" for m in messages])
                    
                    # Context
                    crm_data = user.profile_data.get("__zona_crm", {})
                    aprendizado_data = user.profile_data.get("__zona_aprendizado", {})
                    
                    context = f"DADOS DO USUÁRIO (CRM):\n{json.dumps(crm_data, ensure_ascii=False, indent=2)}\n\n"
                    context += f"APRENDIZADOS ANTERIORES (SE EXISTIREM):\n{json.dumps(aprendizado_data, ensure_ascii=False, indent=2)}\n\n"
                    context += f"HISTÓRICO DE CONVERSAS DO DIA ({target_date_str or 'RECENTE'}):\n{history_text}"
                    
                    # Update JobLog with full prompt context
                    job_log.request_data["context"] = context
                    await session.commit()
                    
                    # Use AgentFactory to properly route to OpenRouter, Google, Custom endpoints, etc.
                    from app.orchestrator.agent_factory import AgentFactory
                    factory = AgentFactory(session)
                    agent_config = await factory.get_agent_config(agent)
                    llm = factory.create_llm(agent_config, session_id=session_id)

                    if agent.output_schema:
                        raw_schema = dict(agent.output_schema)
                        if "parameters" in raw_schema:
                            # It's already an OpenAI Function-style dict
                            schema_dict = raw_schema
                            if "name" not in schema_dict:
                                schema_dict["name"] = "AnalyticsOutput"
                        else:
                            # It's a raw JSON Schema, wrap it
                            schema_dict = {
                                "name": "AnalyticsOutput",
                                "description": "Structured output for user analytics",
                                "parameters": raw_schema
                            }
                        llm = llm.with_structured_output(schema=schema_dict)
                        
                    sys_prompt = agent.system_prompt or "Você é um analista de dados."
                    langchain_msgs = [SystemMessage(content=sys_prompt), HumanMessage(content=context)]
                    
                    response = await llm.ainvoke(langchain_msgs)
                    
                    # Parse Output
                    new_aprendizado = {}
                    if isinstance(response, dict):
                        new_aprendizado = response
                    elif hasattr(response, "content") and isinstance(response.content, str):
                        try:
                            text = response.content.strip()
                            if text.startswith("```json"): text = text[7:-3]
                            elif text.startswith("```"): text = text[3:-3]
                            new_aprendizado = json.loads(text.strip())
                        except Exception:
                            new_aprendizado = {"raw_analysis": response.content}

                    # Attach target date metadata
                    new_aprendizado["data_analise"] = target_date_str or datetime.now().strftime("%Y-%m-%d")

                    # Merge into profile_data["__zona_aprendizado"]
                    current_aprendizado = user.profile_data.get("__zona_aprendizado") or {}
                    current_aprendizado.update(new_aprendizado)
                    user.profile_data["__zona_aprendizado"] = current_aprendizado
                    
                    # Recalculate engagement_score and care_priority
                    from app.services.analytics_service import AnalyticsService
                    analytics_svc = AnalyticsService(session)
                    days_since = 0
                    if user.last_seen_at:
                        days_since = max(0, (datetime.now(timezone.utc) - user.last_seen_at).days)
                    user.engagement_score = analytics_svc._calculate_engagement_score(
                        user.profile_data, user.interaction_count, days_since
                    )
                    user.care_priority = analytics_svc._determine_care_priority(
                        user.engagement_score, days_since
                    )
                    
                    user.last_analyzed_at = datetime.now(timezone.utc)
                    flag_modified(user, "profile_data")
                    
                    # Finalize JobLog
                    duration = int((datetime.now() - start_time).total_seconds() * 1000)
                    job_log.status = "completed"
                    job_log.response_data = new_aprendizado
                    job_log.duration_ms = duration
                    job_log.completed_at = datetime.now(timezone.utc)
                    
                    await session.commit()
                    logger.info(f"[AnalyticsConsumer] Successfully analyzed session {user.session_id} for date {new_aprendizado['data_analise']}")
                    
                    # Fire webhook if configured
                    if config and config.user_webhook_url:
                        try:
                            async with httpx.AsyncClient() as client:
                                payload_out = {
                                    "session_id": user.session_id,
                                    "analytics": new_aprendizado,
                                    "agent": agent.name,
                                    "type": "user_analytics"
                                }
                                await client.post(config.user_webhook_url, json=payload_out, timeout=10.0)
                                logger.info(f"[AnalyticsConsumer] Fired user webhook to {config.user_webhook_url}")
                        except Exception as e:
                            logger.error(f"[AnalyticsConsumer] Failed to fire user webhook: {e}")


                except Exception as ex:
                    logger.error(f"[AnalyticsConsumer] Error running LLM for {session_id}: {ex}")
                    job_log.status = "failed"
                    job_log.error_message = str(ex)
                    duration = int((datetime.now() - start_time).total_seconds() * 1000)
                    job_log.duration_ms = duration
                    job_log.completed_at = datetime.now(timezone.utc)
                    await session.commit()
                    
        except Exception as e:
            logger.error(f"[AnalyticsConsumer] Failed to process message: {e}")

async def start_analytics_consumer():
    """Start listening to analytics queue."""
    logger.info("Starting RabbitMQ consumer for Analytics...")
    await rabbitmq_client.connect()
    
    # Declare the queue if it doesn't exist
    channel = rabbitmq_client.channel
    if not channel:
        logger.error("[AnalyticsConsumer] Failed to connect to RabbitMQ channel")
        return
        
    queue = await channel.declare_queue("analytics_tasks", durable=True)
    
    # Limit concurrent tasks to avoid hitting LLM rate limits and crashing the event loop
    await channel.set_qos(prefetch_count=5)
    
    await queue.consume(process_analytics_message)
    
    logger.info("[AnalyticsConsumer] Listening for analytics_tasks...")
    
    try:
        # Keep alive
        await asyncio.Future()
    except asyncio.CancelledError:
        logger.info("Analytics consumer cancelled.")
