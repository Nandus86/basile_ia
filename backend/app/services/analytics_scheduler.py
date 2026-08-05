import logging
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.analytics_config import AnalyticsConfig
from app.services.workflow_scheduler import workflow_scheduler

logger = logging.getLogger(__name__)

async def run_analytics_agent():
    """
    Function that runs periodically (daily) to invoke the Analyst Agent for users.
    """
    logger.info("[AnalyticsScheduler] Starting daily analytics agent run...")
    try:
        async with AsyncSessionLocal() as session:
            # 1. Fetch AnalyticsConfig to know which agent to use
            config_res = await session.execute(select(AnalyticsConfig).limit(1))
            config = config_res.scalar_one_or_none()
            
            if not config or not config.agent_id:
                logger.warning("[AnalyticsScheduler] No agent configured for Analytics. Skipping run.")
                return
                
            from app.models.user_analytics import UserAnalytics
            from app.models.conversation_message import ConversationMessage
            from app.models.agent import Agent
            from sqlalchemy import select, and_, or_
            from sqlalchemy.orm.attributes import flag_modified
            from datetime import datetime, timezone
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import SystemMessage, HumanMessage
            from app.config import settings
            import json

            # 2. Fetch the Agent
            agent_res = await session.execute(select(Agent).where(Agent.id == config.agent_id))
            agent = agent_res.scalar_one_or_none()
            if not agent:
                logger.error(f"[AnalyticsScheduler] Agent {config.agent_id} not found.")
                return

            # Initialize LLM
            llm = ChatOpenAI(
                model=agent.model or "gpt-4o-mini",
                temperature=float(agent.temperature) if agent.temperature else 0.7,
                api_key=settings.OPENAI_API_KEY
            )
            
            # If agent has structured output, bind it
            if agent.output_schema:
                llm = llm.with_structured_output(schema=agent.output_schema)

            # 3. Find eligible users
            query_users = select(UserAnalytics).where(
                and_(
                    UserAnalytics.interaction_count >= 3,
                    or_(
                        UserAnalytics.last_analyzed_at == None,
                        UserAnalytics.last_seen_at > UserAnalytics.last_analyzed_at
                    )
                )
            )
            users_res = await session.execute(query_users)
            users = users_res.scalars().all()
            
            logger.info(f"[AnalyticsScheduler] Found {len(users)} users pending analysis.")
            
            for user in users:
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
                        continue # nothing to analyze
                        
                    # Format history
                    history_text = "\n".join([f"[{m.created_at.strftime('%H:%M:%S')}] {m.role.upper()}: {m.content}" for m in messages])
                    
                    # Prepare Prompt
                    sys_prompt = agent.system_prompt or "Você é um analista de dados."
                    
                    # User Context
                    crm_data = user.profile_data.get("__zona_crm", {})
                    aprendizado_data = user.profile_data.get("__zona_aprendizado", {})
                    
                    context = f"DADOS DO USUÁRIO (CRM):\n{json.dumps(crm_data, ensure_ascii=False, indent=2)}\n\n"
                    context += f"APRENDIZADOS ANTERIORES (SE EXISTIREM):\n{json.dumps(aprendizado_data, ensure_ascii=False, indent=2)}\n\n"
                    context += f"HISTÓRICO DE CONVERSAS RECENTES:\n{history_text}"
                    
                    langchain_msgs = [
                        SystemMessage(content=sys_prompt),
                        HumanMessage(content=context)
                    ]
                    
                    logger.info(f"[AnalyticsScheduler] Analyzing session {user.session_id} with {len(messages)} new messages.")
                    
                    response = await llm.ainvoke(langchain_msgs)
                    
                    # Response might be a dict if structured output, or AIMessage if not
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
                            
                    # Merge with existing
                    current_aprendizado = user.profile_data.get("__zona_aprendizado", {})
                    current_aprendizado.update(new_aprendizado)
                    user.profile_data["__zona_aprendizado"] = current_aprendizado
                    
                    user.last_analyzed_at = datetime.now(timezone.utc)
                    flag_modified(user, "profile_data")
                    
                    await session.commit()
                    logger.info(f"[AnalyticsScheduler] Successfully analyzed session {user.session_id}")
                    
                except Exception as e:
                    logger.error(f"[AnalyticsScheduler] Failed to analyze session {user.session_id}: {e}")
                    await session.rollback()
            
    except Exception as e:
        logger.error(f"[AnalyticsScheduler] Error running analytics agent: {e}")
    finally:
        logger.info("[AnalyticsScheduler] Finished daily analytics agent run.")

async def sync_analytics_scheduler():
    job_id = "analytics_agent_job"
    
    # Remove existing job
    if workflow_scheduler.scheduler.get_job(job_id):
        workflow_scheduler.scheduler.remove_job(job_id)
        
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AnalyticsConfig).limit(1))
        config = result.scalar_one_or_none()
        
    if not config or not config.is_active or not config.agent_id:
        logger.info("[AnalyticsScheduler] Analytics Agent is inactive or not configured.")
        return
        
    # parse HH:MM
    try:
        hour, minute = config.cron_time.split(":")
        cron_expr = f"{minute} {hour} * * *"
        workflow_scheduler.scheduler.add_job(
            run_analytics_agent,
            trigger=CronTrigger.from_crontab(cron_expr),
            id=job_id,
            replace_existing=True
        )
        logger.info(f"[AnalyticsScheduler] Scheduled Analytics Agent at {config.cron_time} (cron: {cron_expr})")
    except Exception as e:
        logger.error(f"[AnalyticsScheduler] Failed to schedule Analytics Agent: {e}")
