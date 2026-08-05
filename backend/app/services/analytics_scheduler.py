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
            from sqlalchemy import select, and_, or_

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
            
            from app.services.rabbitmq_service import rabbitmq_client
            await rabbitmq_client.connect()
            
            for user in users:
                try:
                    payload = {
                        "session_id": user.session_id,
                        "agent_id": config.agent_id
                    }
                    await rabbitmq_client.publish_message(
                        exchange_name="",
                        routing_key="analytics_tasks",
                        message_body=payload
                    )
                    logger.info(f"[AnalyticsScheduler] Queued session {user.session_id} for analysis")
                except Exception as e:
                    logger.error(f"[AnalyticsScheduler] Failed to queue session {user.session_id}: {e}")
                    
            
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
