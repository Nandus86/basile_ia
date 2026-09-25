import logging
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.analytics_config import AnalyticsConfig
from app.services.workflow_scheduler import workflow_scheduler

logger = logging.getLogger(__name__)

async def _resolve_church_name(session, church_id: str) -> str:
    """Resolve o nome real da igreja a partir do profile_data dos usuários."""
    from app.models.user_analytics import UserAnalytics
    res = await session.execute(
        select(UserAnalytics.profile_data).where(UserAnalytics.church_id == church_id).limit(1)
    )
    profile = res.scalar_one_or_none()
    if profile and isinstance(profile, dict):
        crm = profile.get("__zona_crm", {})
        name = crm.get("church_name") or crm.get("Igreja Sede")
        if name:
            return name
    return church_id

from datetime import datetime, date, time, timezone, timedelta
try:
    from zoneinfo import ZoneInfo
except ImportError:
    import pytz
    ZoneInfo = pytz.timezone


def get_utc_day_range(target_date=None, tz_name="America/Sao_Paulo"):
    """
    Retorna (start_utc, end_utc, target_date_obj) para um dia específico
    convertido do timezone local (ex: America/Sao_Paulo) para UTC.
    Se target_date for None, assume ontem (D-1).
    """
    try:
        user_tz = ZoneInfo(tz_name)
    except Exception:
        user_tz = ZoneInfo("America/Sao_Paulo")

    now_local = datetime.now(user_tz)
    if target_date is None:
        target_date_obj = (now_local - timedelta(days=1)).date()
    elif isinstance(target_date, str):
        clean_str = target_date.strip()
        if "T" in clean_str:
            clean_str = clean_str.split("T")[0]
        target_date_obj = date.fromisoformat(clean_str)
    elif isinstance(target_date, datetime):
        if target_date.tzinfo is not None:
            target_date_obj = target_date.astimezone(user_tz).date()
        else:
            target_date_obj = target_date.date()
    elif isinstance(target_date, date):
        target_date_obj = target_date
    else:
        target_date_obj = (now_local - timedelta(days=1)).date()

    start_local = datetime.combine(target_date_obj, time.min).replace(tzinfo=user_tz)
    end_local = datetime.combine(target_date_obj, time.max).replace(tzinfo=user_tz)

    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    return start_utc, end_utc, target_date_obj


async def run_analytics_agent(target_date=None):
    """
    Function that runs periodically (daily) to invoke the Analyst Agent for users
    who actually sent messages on the target day (defaults to yesterday D-1).
    """
    start_utc, end_utc, target_date_obj = get_utc_day_range(target_date)

    # Distributed lock across multiple Uvicorn workers
    from app.redis_client import redis_client
    try:
        r_client = await redis_client.connect()
        lock_key = f"lock:scheduler:user_analytics_daily:{target_date_obj}"
        acquired = await r_client.set(lock_key, "1", nx=True, ex=7200)
        if not acquired:
            logger.info(f"[AnalyticsScheduler] Another worker already running user analytics for {target_date_obj}. Skipping.")
            return
    except Exception as e:
        logger.warning(f"[AnalyticsScheduler] Redis lock warning: {e}")

    logger.info(f"[AnalyticsScheduler] Starting daily analytics run for date {target_date_obj} (UTC {start_utc} to {end_utc})...")
    try:
        async with AsyncSessionLocal() as session:
            # 1. Fetch AnalyticsConfig to know which agent to use
            config_res = await session.execute(select(AnalyticsConfig).limit(1))
            config = config_res.scalar_one_or_none()
            
            if not config or not config.is_active or not config.agent_id:
                logger.info("[AnalyticsScheduler] Analytics Agent is inactive or not configured. Skipping run.")
                return
                
            from app.models.conversation_message import ConversationMessage
            from sqlalchemy import select, func

            # 2. Find sessions that actually interacted on the target day (role == 'user')
            query_active = (
                select(
                    ConversationMessage.session_id,
                    func.count(ConversationMessage.id).label("user_msg_count")
                )
                .where(
                    ConversationMessage.role == "user",
                    ConversationMessage.created_at >= start_utc,
                    ConversationMessage.created_at <= end_utc
                )
                .group_by(ConversationMessage.session_id)
            )
            res = await session.execute(query_active)
            active_sessions = res.all()
            
            logger.info(f"[AnalyticsScheduler] Found {len(active_sessions)} active users who interacted on {target_date_obj}.")
            
            from app.services.rabbitmq_service import rabbitmq_client
            await rabbitmq_client.connect()
            
            queued = 0
            for row in active_sessions:
                session_id = row[0]
                msg_count = row[1]
                try:
                    payload = {
                        "session_id": session_id,
                        "agent_id": str(config.agent_id),
                        "target_date": target_date_obj.isoformat(),
                        "start_time": start_utc.isoformat(),
                        "end_time": end_utc.isoformat(),
                        "daily_msg_count": msg_count
                    }
                    await rabbitmq_client.publish_message(
                        exchange_name="",
                        routing_key="analytics_tasks",
                        message_body=payload
                    )
                    queued += 1
                except Exception as e:
                    logger.error(f"[AnalyticsScheduler] Failed to queue session {session_id}: {e}")
                    
            logger.info(f"[AnalyticsScheduler] Enqueued {queued} users for date {target_date_obj}.")
    except Exception as e:
        logger.error(f"[AnalyticsScheduler] Error running analytics agent: {e}")
    finally:
        logger.info("[AnalyticsScheduler] Finished daily analytics agent run.")

async def queue_report_task(level: str, period_type: str, entity_id: str, entity_name: str, start_time, end_time, force: bool = False):
    """
    Creates or updates an AnalyticsReport and queues it.
    Guarantees exactly one report per entity per period.
    When force=True (manual run), replaces whatever report already exists for the day and cleans up duplicates.
    """
    from app.models.analytics_report import AnalyticsReport
    from app.services.rabbitmq_service import rabbitmq_client
    from app.redis_client import redis_client
    from sqlalchemy import select, or_, cast, Date, func, case
    import uuid

    if period_type == "daily":
        start_time, end_time, target_date_obj = get_utc_day_range(start_time)
    else:
        target_date_obj = start_time.date() if hasattr(start_time, 'date') else start_time

    # Distributed lock to prevent race conditions during insertion/queuing
    r_client = None
    lock_key = f"lock:queue_report:{level}:{period_type}:{entity_id}:{target_date_obj}"
    try:
        r_client = await redis_client.connect()
        acquired = await r_client.set(lock_key, "1", nx=True, ex=60)
        if not acquired and not force:
            logger.info(f"[AnalyticsScheduler] Report task for {entity_id} ({level}/{period_type}) on {target_date_obj} is already being processed. Skipping.")
            return
    except Exception as e:
        logger.warning(f"[AnalyticsScheduler] Redis lock warning: {e}")

    try:
        async with AsyncSessionLocal() as session:
            if not force:
                cfg_res = await session.execute(select(AnalyticsConfig).limit(1))
                cfg = cfg_res.scalar_one_or_none()
                if not cfg or not cfg.is_active:
                    logger.info(f"[AnalyticsScheduler] Skipping queue_report_task for {entity_name} ({level}/{period_type}): Analytics is inactive.")
                    return

            # Check if already generated for this exact period (matching UTC or Sao Paulo date)
            date_filters = [cast(AnalyticsReport.period_start, Date) == target_date_obj]
            try:
                date_filters.append(cast(func.timezone('America/Sao_Paulo', AnalyticsReport.period_start), Date) == target_date_obj)
            except Exception:
                pass

            existing_stmt = (
                select(AnalyticsReport)
                .where(
                    AnalyticsReport.level == level,
                    AnalyticsReport.period_type == period_type,
                    AnalyticsReport.entity_id == str(entity_id),
                    or_(*date_filters)
                )
                .order_by(
                    case((AnalyticsReport.status == "completed", 1), else_=2),
                    AnalyticsReport.completed_at.desc().nullslast(),
                    AnalyticsReport.id.desc()
                )
            )
            existing_res = await session.execute(existing_stmt)
            existing_recs = existing_res.scalars().all()

            if existing_recs:
                primary_rec = existing_recs[0]
                
                # Delete surplus duplicate reports so that ONLY ONE remains
                if len(existing_recs) > 1:
                    for dup in existing_recs[1:]:
                        logger.info(f"[AnalyticsScheduler] Removing duplicate report {dup.id} for {entity_id} on {target_date_obj}")
                        await session.delete(dup)
                    await session.flush()

                if force:
                    # Replace whatever is there with fresh pending state
                    primary_rec.status = "pending"
                    primary_rec.period_start = start_time
                    primary_rec.period_end = end_time
                    if entity_name:
                        primary_rec.entity_name = entity_name
                    primary_rec.stats = None
                    primary_rec.report_content = None
                    primary_rec.sub_reports = []
                    primary_rec.error_message = None
                    primary_rec.completed_at = None
                    await session.commit()

                    await rabbitmq_client.connect()
                    await rabbitmq_client.publish_message(
                        exchange_name="",
                        routing_key="analytics_reports_queue",
                        message_body={"report_id": str(primary_rec.id), "force": True}
                    )
                    logger.info(f"[AnalyticsScheduler] Replaced and re-queued report {primary_rec.id} ({level}/{period_type}) for {target_date_obj} (force=True)")
                    return
                else:
                    await session.commit()
                    logger.info(f"[AnalyticsScheduler] Report {level}/{period_type} for {entity_id} at {target_date_obj} already exists. Skipping.")
                    return

            # No existing report — create brand new one
            report = AnalyticsReport(
                id=uuid.uuid4(),
                level=level,
                period_type=period_type,
                entity_id=str(entity_id),
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
                message_body={"report_id": str(report.id), "force": force}
            )
            logger.info(f"[AnalyticsScheduler] Queued new report {report.id} ({level}/{period_type}, force={force})")
    finally:
        if r_client:
            try:
                await r_client.delete(lock_key)
            except Exception:
                pass

async def run_church_daily_reports():
    logger.info("[AnalyticsScheduler] Starting church daily reports...")
    from app.models.user_analytics import UserAnalytics
    from sqlalchemy import select
    
    start_time, end_time, target_date_obj = get_utc_day_range()

    from app.redis_client import redis_client
    try:
        r_client = await redis_client.connect()
        lock_key = f"lock:scheduler:church_daily_reports:{target_date_obj}"
        acquired = await r_client.set(lock_key, "1", nx=True, ex=7200)
        if not acquired:
            logger.info(f"[AnalyticsScheduler] Another worker already running church daily reports for {target_date_obj}. Skipping.")
            return
    except Exception as e:
        logger.warning(f"[AnalyticsScheduler] Redis lock warning: {e}")

    async with AsyncSessionLocal() as session:
        cfg_res = await session.execute(select(AnalyticsConfig).limit(1))
        config = cfg_res.scalar_one_or_none()
        if not config or not config.is_active or not config.church_agent_id:
            logger.info("[AnalyticsScheduler] Church daily reports skipped: Analytics is inactive or no church agent configured.")
            return

        churches_res = await session.execute(select(UserAnalytics.church_id).where(UserAnalytics.church_id != None).distinct())
        church_ids = churches_res.scalars().all()
        
        for cid in church_ids:
            name = await _resolve_church_name(session, cid)
            await queue_report_task("church", "daily", cid, name, start_time, end_time)

async def run_system_daily_reports():
    logger.info("[AnalyticsScheduler] Starting system daily reports...")
    start_time, end_time, target_date_obj = get_utc_day_range()

    from app.redis_client import redis_client
    try:
        r_client = await redis_client.connect()
        lock_key = f"lock:scheduler:system_daily_reports:{target_date_obj}"
        acquired = await r_client.set(lock_key, "1", nx=True, ex=7200)
        if not acquired:
            logger.info(f"[AnalyticsScheduler] Another worker already running system daily reports for {target_date_obj}. Skipping.")
            return
    except Exception as e:
        logger.warning(f"[AnalyticsScheduler] Redis lock warning: {e}")

    async with AsyncSessionLocal() as session:
        cfg_res = await session.execute(select(AnalyticsConfig).limit(1))
        config = cfg_res.scalar_one_or_none()
        if not config or not config.is_active or not config.system_agent_id:
            logger.info("[AnalyticsScheduler] System daily reports skipped: Analytics is inactive or no system agent configured.")
            return
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

    from app.redis_client import redis_client
    try:
        r_client = await redis_client.connect()
        lock_key = f"lock:scheduler:church_weekly_reports:{start_time.date()}"
        acquired = await r_client.set(lock_key, "1", nx=True, ex=7200)
        if not acquired:
            logger.info(f"[AnalyticsScheduler] Another worker already running church weekly reports for {start_time.date()}. Skipping.")
            return
    except Exception as e:
        logger.warning(f"[AnalyticsScheduler] Redis lock warning: {e}")
    
    async with AsyncSessionLocal() as session:
        cfg_res = await session.execute(select(AnalyticsConfig).limit(1))
        config = cfg_res.scalar_one_or_none()
        if not config or not config.is_active or not config.church_agent_id:
            logger.info("[AnalyticsScheduler] Church weekly reports skipped: Analytics is inactive or no church agent configured.")
            return

        churches_res = await session.execute(select(UserAnalytics.church_id).where(UserAnalytics.church_id != None).distinct())
        church_ids = churches_res.scalars().all()
        
        for cid in church_ids:
            name = await _resolve_church_name(session, cid)
            await queue_report_task("church", "weekly", cid, name, start_time, end_time)

        
async def run_system_weekly_reports():
    logger.info("[AnalyticsScheduler] Starting system weekly reports...")
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    start_time = (now - timedelta(days=now.weekday() + 7)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(days=7, microseconds=-1)

    from app.redis_client import redis_client
    try:
        r_client = await redis_client.connect()
        lock_key = f"lock:scheduler:system_weekly_reports:{start_time.date()}"
        acquired = await r_client.set(lock_key, "1", nx=True, ex=7200)
        if not acquired:
            logger.info(f"[AnalyticsScheduler] Another worker already running system weekly reports for {start_time.date()}. Skipping.")
            return
    except Exception as e:
        logger.warning(f"[AnalyticsScheduler] Redis lock warning: {e}")

    async with AsyncSessionLocal() as session:
        cfg_res = await session.execute(select(AnalyticsConfig).limit(1))
        config = cfg_res.scalar_one_or_none()
        if not config or not config.is_active or not config.system_agent_id:
            logger.info("[AnalyticsScheduler] System weekly reports skipped: Analytics is inactive or no system agent configured.")
            return
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
    
    from app.redis_client import redis_client
    try:
        r_client = await redis_client.connect()
        lock_key = f"lock:scheduler:church_monthly_reports:{start_time.date()}"
        acquired = await r_client.set(lock_key, "1", nx=True, ex=7200)
        if not acquired:
            logger.info(f"[AnalyticsScheduler] Another worker already running church monthly reports for {start_time.date()}. Skipping.")
            return
    except Exception as e:
        logger.warning(f"[AnalyticsScheduler] Redis lock warning: {e}")

    async with AsyncSessionLocal() as session:
        cfg_res = await session.execute(select(AnalyticsConfig).limit(1))
        config = cfg_res.scalar_one_or_none()
        if not config or not config.is_active or not config.church_agent_id:
            logger.info("[AnalyticsScheduler] Church monthly reports skipped: Analytics is inactive or no church agent configured.")
            return

        churches_res = await session.execute(select(UserAnalytics.church_id).where(UserAnalytics.church_id != None).distinct())
        church_ids = churches_res.scalars().all()
        
        for cid in church_ids:
            name = await _resolve_church_name(session, cid)
            await queue_report_task("church", "monthly", cid, name, start_time, end_time)

async def run_system_monthly_reports():
    logger.info("[AnalyticsScheduler] Starting system monthly reports...")
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    first_day_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_time = first_day_this_month - timedelta(microseconds=1)
    start_time = end_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    from app.redis_client import redis_client
    try:
        r_client = await redis_client.connect()
        lock_key = f"lock:scheduler:system_monthly_reports:{start_time.date()}"
        acquired = await r_client.set(lock_key, "1", nx=True, ex=7200)
        if not acquired:
            logger.info(f"[AnalyticsScheduler] Another worker already running system monthly reports for {start_time.date()}. Skipping.")
            return
    except Exception as e:
        logger.warning(f"[AnalyticsScheduler] Redis lock warning: {e}")

    async with AsyncSessionLocal() as session:
        cfg_res = await session.execute(select(AnalyticsConfig).limit(1))
        config = cfg_res.scalar_one_or_none()
        if not config or not config.is_active or not config.system_agent_id:
            logger.info("[AnalyticsScheduler] System monthly reports skipped: Analytics is inactive or no system agent configured.")
            return
        await queue_report_task("system", "monthly", "system", "Global Basile", start_time, end_time)

def _parse_time_parts(time_str: str, default_h: int = 3, default_m: int = 0):
    try:
        if time_str and ":" in time_str:
            parts = time_str.strip().split(":")
            return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return default_h, default_m

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
        tz = "America/Sao_Paulo"

        # USER DAILY (Ex: 03:00)
        if config.agent_id:
            h, m = _parse_time_parts(config.cron_time, 3, 0)
            workflow_scheduler.scheduler.add_job(
                run_analytics_agent,
                trigger=CronTrigger(hour=h, minute=m, timezone=tz),
                id="analytics_agent_job", replace_existing=True
            )
            logger.info(f"[AnalyticsScheduler] Scheduled User Analytics daily job at {h:02d}:{m:02d} ({tz})")
            
        # CHURCH DAILY (Ex: 04:00)
        if config.church_agent_id:
            h_church, m_church = _parse_time_parts(config.church_report_time, 4, 0)
            workflow_scheduler.scheduler.add_job(
                run_church_daily_reports,
                trigger=CronTrigger(hour=h_church, minute=m_church, timezone=tz),
                id="church_daily_report_job", replace_existing=True
            )
            # CHURCH WEEKLY (Sunday at same hour)
            workflow_scheduler.scheduler.add_job(
                run_church_weekly_reports,
                trigger=CronTrigger(day_of_week="sun", hour=h_church, minute=m_church, timezone=tz),
                id="church_weekly_report_job", replace_existing=True
            )
            # CHURCH MONTHLY (Day 1 at same hour)
            workflow_scheduler.scheduler.add_job(
                run_church_monthly_reports,
                trigger=CronTrigger(day=1, hour=h_church, minute=m_church, timezone=tz),
                id="church_monthly_report_job", replace_existing=True
            )
            logger.info(f"[AnalyticsScheduler] Scheduled Church reports (daily/weekly/monthly) at {h_church:02d}:{m_church:02d} ({tz})")
            
        # SYSTEM DAILY (Ex: 04:30)
        if config.system_agent_id:
            h_sys, m_sys = _parse_time_parts(config.system_report_time, 4, 30)
            workflow_scheduler.scheduler.add_job(
                run_system_daily_reports,
                trigger=CronTrigger(hour=h_sys, minute=m_sys, timezone=tz),
                id="system_daily_report_job", replace_existing=True
            )
            # SYSTEM WEEKLY (Sunday at same hour)
            workflow_scheduler.scheduler.add_job(
                run_system_weekly_reports,
                trigger=CronTrigger(day_of_week="sun", hour=h_sys, minute=m_sys, timezone=tz),
                id="system_weekly_report_job", replace_existing=True
            )
            # SYSTEM MONTHLY (Day 1 at same hour)
            workflow_scheduler.scheduler.add_job(
                run_system_monthly_reports,
                trigger=CronTrigger(day=1, hour=h_sys, minute=m_sys, timezone=tz),
                id="system_monthly_report_job", replace_existing=True
            )
            logger.info(f"[AnalyticsScheduler] Scheduled System reports (daily/weekly/monthly) at {h_sys:02d}:{m_sys:02d} ({tz})")
            
        logger.info(f"[AnalyticsScheduler] Synced report crons successfully from DB config.")
    except Exception as e:
        logger.error(f"[AnalyticsScheduler] Failed to schedule Analytics crons: {e}")
