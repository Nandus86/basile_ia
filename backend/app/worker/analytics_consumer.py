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
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

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

            if not session_id or not agent_id:
                logger.error(f"[AnalyticsConsumer] Invalid payload: {payload}")
                return

            logger.info(f"[AnalyticsConsumer] Processing analytics for session {session_id}")

            async with async_session_maker() as session:
                # Get the Agent
                agent_res = await session.execute(select(Agent).where(Agent.id == agent_id))
                agent = agent_res.scalar_one_or_none()
                if not agent:
                    logger.error(f"[AnalyticsConsumer] Agent {agent_id} not found.")
                    return
                
                # Get UserAnalytics
                user_res = await session.execute(
                    select(UserAnalytics).where(UserAnalytics.session_id == session_id)
                )
                user = user_res.scalar_one_or_none()
                if not user:
                    logger.error(f"[AnalyticsConsumer] UserAnalytics for {session_id} not found.")
                    return

                # Logging to JobLogs (so it appears on UI)
                from app.models.job_log import JobLog
                import uuid
                job_log = JobLog(
                    id=uuid.uuid4(),
                    job_id=str(uuid.uuid4()),
                    webhook_path="/internal/analytics_agent",
                    status="processing",
                    request_data={"session_id": session_id, "agent": agent.name}
                )
                session.add(job_log)
                await session.commit()
                
                start_time = datetime.now()

                try:
                    # Fetch recent messages
                    msg_query = select(ConversationMessage).where(
                        ConversationMessage.session_id == user.session_id
                    )
                    if user.last_analyzed_at:
                        msg_query = msg_query.where(ConversationMessage.created_at > user.last_analyzed_at)
                    msg_query = msg_query.order_by(ConversationMessage.created_at.asc())
                    
                    msg_res = await session.execute(msg_query)
                    messages = msg_res.scalars().all()
                    
                    if not messages:
                        # Nothing to do
                        job_log.status = "completed"
                        job_log.response_data = {"status": "no_new_messages"}
                        await session.commit()
                        return
                    
                    # Format history
                    history_text = "\n".join([f"[{m.created_at.strftime('%H:%M:%S')}] {m.role.upper()}: {m.content}" for m in messages])
                    
                    # Context
                    crm_data = user.profile_data.get("__zona_crm", {})
                    aprendizado_data = user.profile_data.get("__zona_aprendizado", {})
                    
                    context = f"DADOS DO USUÁRIO (CRM):\n{json.dumps(crm_data, ensure_ascii=False, indent=2)}\n\n"
                    context += f"APRENDIZADOS ANTERIORES (SE EXISTIREM):\n{json.dumps(aprendizado_data, ensure_ascii=False, indent=2)}\n\n"
                    context += f"HISTÓRICO DE CONVERSAS RECENTES:\n{history_text}"
                    
                    # Update JobLog with full prompt context
                    job_log.request_data["context"] = context
                    await session.commit()
                    
                    # LLM
                    llm = ChatOpenAI(
                        model=agent.model or "gpt-4o-mini",
                        temperature=float(agent.temperature) if agent.temperature else 0.7,
                        api_key=settings.OPENAI_API_KEY
                    )
                    if agent.output_schema:
                        llm = llm.with_structured_output(schema=agent.output_schema)
                        
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
                        except:
                            new_aprendizado = {"raw_analysis": response.content}

                    # Merge
                    current_aprendizado = user.profile_data.get("__zona_aprendizado", {})
                    current_aprendizado.update(new_aprendizado)
                    user.profile_data["__zona_aprendizado"] = current_aprendizado
                    
                    user.last_analyzed_at = datetime.now(timezone.utc)
                    flag_modified(user, "profile_data")
                    
                    # Finalize JobLog
                    duration = int((datetime.now() - start_time).total_seconds() * 1000)
                    job_log.status = "completed"
                    job_log.response_data = new_aprendizado
                    job_log.duration_ms = duration
                    job_log.completed_at = datetime.now(timezone.utc)
                    
                    await session.commit()
                    logger.info(f"[AnalyticsConsumer] Successfully analyzed session {user.session_id}")

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
    await queue.consume(process_analytics_message)
    
    logger.info("[AnalyticsConsumer] Listening for analytics_tasks...")
    
    try:
        # Keep alive
        await asyncio.Future()
    except asyncio.CancelledError:
        logger.info("Analytics consumer cancelled.")
