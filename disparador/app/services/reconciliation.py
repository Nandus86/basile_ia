"""
Disparador Stagnant Campaign Watchdog / Reconciler
Detects campaigns stuck in 'running' that have no active workers and pending contacts,
and safely re-enqueues the pending contacts.
"""
import asyncio
import logging
from datetime import datetime, timezone
import json

from app.services.redis_service import disparador_redis
from app.services.rabbitmq_service import disparador_rmq
from app.services.dispatcher_engine import is_within_time_window

logger = logging.getLogger(__name__)

async def reconcile_stagnant_campaigns():
    """Scan and resume campaigns stuck in 'running' with no active activity."""
    try:
        await disparador_redis.ensure_connected()
        campaigns = await disparador_redis.list_campaigns()
        if not campaigns:
            return
            
        now = datetime.now(timezone.utc)
        
        for c in campaigns:
            sid = c.get("service_id")
            if not sid:
                continue
            status = c.get("status")
            if status != "running":
                continue
                
            # Check if paused
            if await disparador_redis.is_paused(sid):
                continue
                
            total = c.get("total", 0)
            sent = c.get("sent", 0)
            failed = c.get("failed", 0)
            
            if (sent + failed) >= total and total > 0:
                await disparador_redis.complete_campaign(sid)
                continue
                
            # Check contacts to find pending ones and last activity time
            contacts = await disparador_redis.get_campaign_contacts(sid)
            pending_contacts = [ct for ct in contacts if ct.get("status") in ("pending", "waiting", None)]
            if not pending_contacts:
                if (sent + failed) >= total:
                    await disparador_redis.complete_campaign(sid)
                continue
                
            # Check last updated timestamp across contacts
            latest_update = None
            for ct in contacts:
                upd_str = ct.get("updated_at")
                if upd_str:
                    try:
                        upd_dt = datetime.fromisoformat(upd_str.replace("Z", "+00:00"))
                        if not latest_update or upd_dt > latest_update:
                            latest_update = upd_dt
                    except Exception:
                        pass
                        
            # If updated in the last 25 minutes, it may be actively dispatching
            if latest_update:
                elapsed = (now - latest_update).total_seconds()
                if elapsed < 1500:
                    continue
            else:
                started_str = c.get("started_at")
                if started_str:
                    try:
                        started_dt = datetime.fromisoformat(started_str.replace("Z", "+00:00"))
                        if (now - started_dt).total_seconds() < 1500:
                            continue
                    except Exception:
                        pass

            # Check if currently active in active_campaigns_lock in consumer
            from app.worker.consumer import active_campaigns_lock
            camp_key = c.get("campaign_key")
            if camp_key and camp_key in active_campaigns_lock:
                continue
                
            # Check if currently within time window
            config_path = c.get("config_path")
            if not config_path:
                continue
                
            from app.database import async_session_maker
            from sqlalchemy.future import select
            from app.models.dispatcher_config import DispatcherConfig
            
            async with async_session_maker() as db:
                q = select(DispatcherConfig).where(DispatcherConfig.path == config_path)
                res = await db.execute(q)
                cfg = res.scalar_one_or_none()
                
            if not cfg or not cfg.is_active:
                continue
                
            payloads = await disparador_redis.get_campaign_payloads(sid)
            input_payload = payloads.get("input", {}) if payloads else {}
            
            if not is_within_time_window(cfg, input_payload):
                # Outside allowed time window, let it wait for window opening
                continue
                
            logger.warning(
                f"[Watchdog] Found stagnant campaign: service_id={sid} (path={config_path}, "
                f"sent={sent}/{total}, pending={len(pending_contacts)}). Auto-reconciling pending contacts..."
            )
            
            # Use resume logic to safely re-enqueue pending contacts
            from app.api.dashboard import resume_pending_campaign
            async with async_session_maker() as db:
                await resume_pending_campaign(sid, db)
                
    except Exception as e:
        logger.error(f"[Watchdog] Error during stagnant campaign reconciliation: {e}", exc_info=True)


async def start_reconciliation_watchdog():
    """Background task running reconciliation every 15 minutes."""
    await asyncio.sleep(60) # Initial warmup delay
    while True:
        try:
            await reconcile_stagnant_campaigns()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[Watchdog] Unhandled exception in watchdog: {e}", exc_info=True)
        await asyncio.sleep(900) # Every 15 minutes
