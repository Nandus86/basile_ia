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

async def queue_report_task(level: str, period_type: str, entity_id: str, entity_name: str, start_time, end_time):
    """Creates a pending AnalyticsReport and queues it."""
    from app.models.analytics_report import AnalyticsReport
    from app.services.rabbitmq_service import rabbitmq_client
    import uuid
    
    async with AsyncSessionLocal() as session:
        # Check if already generated for this exact period
        from sqlalchemy import select
        existing = await session.execute(
            select(AnalyticsReport).where(
                AnalyticsReport.level == level,
                AnalyticsReport.period_type == period_type,
                AnalyticsReport.entity_id == entity_id,
                AnalyticsReport.period_start == start_time
            )
        )
        if existing.scalar_one_or_none():
            logger.info(f"[AnalyticsScheduler] Report {level}/{period_type} for {entity_id} at {start_time} already exists.")
            return

        report = AnalyticsReport(
            id=uuid.uuid4(),
            level=level,
            period_type=period_type,
            entity_id=entity_id,
            entity_name=entity_name,
            period_start=start_time,
            period_end=end_time,
            status="pending"
        )
        session.add(report)
        await session.commit()
        
        await rabbitmq_client.connect()
        await rabbitmq_client.publish_message(
            exchange_name="",
            routing_key="analytics_reports_queue",
            message_body={"report_id": str(report.id)}
        )
        logger.info(f"[AnalyticsScheduler] Queued report {report.id} ({level}/{period_type})")

async def run_church_daily_reports():
    logger.info("[AnalyticsScheduler] Starting church daily reports...")
    from datetime import datetime, timezone, timedelta
    from app.models.user_analytics import UserAnalytics
    from sqlalchemy import select
    
    now = datetime.now(timezone.utc)
    start_time = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(days=1, microseconds=-1)
    
    async with AsyncSessionLocal() as session:
        churches_res = await session.execute(select(UserAnalytics.church_id).where(UserAnalytics.church_id != None).distinct())
        church_ids = churches_res.scalars().all()
        
    for cid in church_ids:
        # For now, entity_name = entity_id (frontend will map it, or we could fetch it)
        await queue_report_task("church", "daily", cid, cid, start_time, end_time)

async def run_system_daily_reports():
    logger.info("[AnalyticsScheduler] Starting system daily reports...")
    from datetime import datetime, timezone, timedelta
    
    now = datetime.now(timezone.utc)
    start_time = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(days=1, microseconds=-1)
    
    await queue_report_task("system", "daily", "system", "Global Basile", start_time, end_time)
    
async def run_church_weekly_reports():
    logger.info("[AnalyticsScheduler] Starting church weekly reports...")
    from datetime import datetime, timezone, timedelta
    from app.models.user_analytics import UserAnalytics
    from sqlalchemy import select
    
    now = datetime.now(timezone.utc)
    # Get last monday
    start_time = (now - timedelta(days=now.weekday() + 7)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(days=7, microseconds=-1)
    
    async with AsyncSessionLocal() as session:
        churches_res = await session.execute(select(UserAnalytics.church_id).where(UserAnalytics.church_id != None).distinct())
        church_ids = churches_res.scalars().all()
        
    for cid in church_ids:
        await queue_report_task("church", "weekly", cid, cid, start_time, end_time)
        
async def run_system_weekly_reports():
    logger.info("[AnalyticsScheduler] Starting system weekly reports...")
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    start_time = (now - timedelta(days=now.weekday() + 7)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(days=7, microseconds=-1)
    await queue_report_task("system", "weekly", "system", "Global Basile", start_time, end_time)
    
async def run_church_monthly_reports():
    logger.info("[AnalyticsScheduler] Starting church monthly reports...")
    from datetime import datetime, timezone, timedelta
    from app.models.user_analytics import UserAnalytics
    from sqlalchemy import select
    
    now = datetime.now(timezone.utc)
    # Get first day of last month
    first_day_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_time = first_day_this_month - timedelta(microseconds=1)
    start_time = end_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    async with AsyncSessionLocal() as session:
        churches_res = await session.execute(select(UserAnalytics.church_id).where(UserAnalytics.church_id != None).distinct())
        church_ids = churches_res.scalars().all()
        
    for cid in church_ids:
        await queue_report_task("church", "monthly", cid, cid, start_time, end_time)

async def run_system_monthly_reports():
    logger.info("[AnalyticsScheduler] Starting system monthly reports...")
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    first_day_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_time = first_day_this_month - timedelta(microseconds=1)
    start_time = end_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    await queue_report_task("system", "monthly", "system", "Global Basile", start_time, end_time)

async def sync_analytics_scheduler():
    job_ids = [
        "analytics_agent_job",
        "church_daily_report_job",
        "system_daily_report_job",
        "church_weekly_report_job",
        "system_weekly_report_job",
        "church_monthly_report_job",
        "system_monthly_report_job"
    ]
    
    # Remove existing jobs
    for job_id in job_ids:
        if workflow_scheduler.scheduler.get_job(job_id):
            workflow_scheduler.scheduler.remove_job(job_id)
        
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AnalyticsConfig).limit(1))
        config = result.scalar_one_or_none()
        
    if not config or not config.is_active:
        logger.info("[AnalyticsScheduler] Analytics Agent is inactive or not configured.")
        return
        
    try:
        # USER DAILY (Ex: 03:00)
        if config.agent_id:
            hour, minute = config.cron_time.split(":")
            workflow_scheduler.scheduler.add_job(
                run_analytics_agent,
                trigger=CronTrigger.from_crontab(f"{minute} {hour} * * *"),
                id="analytics_agent_job", replace_existing=True
            )
            
        # CHURCH DAILY (Ex: 04:00)
        if config.church_agent_id:
            hour, minute = config.church_report_time.split(":")
            workflow_scheduler.scheduler.add_job(
                run_church_daily_reports,
                trigger=CronTrigger.from_crontab(f"{minute} {hour} * * *"),
                id="church_daily_report_job", replace_existing=True
            )
            # CHURCH WEEKLY (Sunday at same hour)
            workflow_scheduler.scheduler.add_job(
                run_church_weekly_reports,
                trigger=CronTrigger.from_crontab(f"{minute} {hour} * * 0"),
                id="church_weekly_report_job", replace_existing=True
            )
            # CHURCH MONTHLY (Day 1 at same hour)
            workflow_scheduler.scheduler.add_job(
                run_church_monthly_reports,
                trigger=CronTrigger.from_crontab(f"{minute} {hour} 1 * *"),
                id="church_monthly_report_job", replace_existing=True
            )
            
        # SYSTEM DAILY (Ex: 04:30)
        if config.system_agent_id:
            hour, minute = config.system_report_time.split(":")
            workflow_scheduler.scheduler.add_job(
                run_system_daily_reports,
                trigger=CronTrigger.from_crontab(f"{minute} {hour} * * *"),
                id="system_daily_report_job", replace_existing=True
            )
            # SYSTEM WEEKLY
            workflow_scheduler.scheduler.add_job(
                run_system_weekly_reports,
                trigger=CronTrigger.from_crontab(f"{minute} {hour} * * 0"),
                id="system_weekly_report_job", replace_existing=True
            )
            # SYSTEM MONTHLY
            workflow_scheduler.scheduler.add_job(
                run_system_monthly_reports,
                trigger=CronTrigger.from_crontab(f"{minute} {hour} 1 * *"),
                id="system_monthly_report_job", replace_existing=True
            )
            
        logger.info(f"[AnalyticsScheduler] Synced 7 report crons from DB config.")
    except Exception as e:
        logger.error(f"[AnalyticsScheduler] Failed to schedule Analytics crons: {e}")
