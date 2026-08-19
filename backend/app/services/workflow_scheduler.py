import logging
from typing import Dict
from uuid import UUID
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.workflow import Workflow
from app.services.workflow_engine import WorkflowEngine

logger = logging.getLogger(__name__)

class WorkflowScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._jobs: Dict[str, str] = {}  # workflow_id -> job_id

    def start(self):
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("[WorkflowScheduler] Scheduler started successfully.")
            
        if not self.scheduler.get_job("workflow_timeout_checker"):
            self.scheduler.add_job(
                func=self.check_workflow_timeouts,
                trigger="interval",
                seconds=15,
                id="workflow_timeout_checker",
                replace_existing=True
            )
            logger.info("[WorkflowScheduler] Scheduled workflow timeout checker (every 15s)")

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("[WorkflowScheduler] Scheduler shut down successfully.")

    async def check_workflow_timeouts(self):
        """Check paused workflow executions and expire those past timeout_seconds."""
        from datetime import datetime, timezone
        from app.models.workflow_execution import WorkflowExecution
        now = datetime.now(timezone.utc)
        
        async with AsyncSessionLocal() as db:
            try:
                stmt = select(WorkflowExecution).where(WorkflowExecution.status == "paused")
                res = await db.execute(stmt)
                paused_execs = res.scalars().all()
                
                for exec_rec in paused_execs:
                    try:
                        wf_res = await db.execute(select(Workflow).where(Workflow.id == exec_rec.workflow_id))
                        wf = wf_res.scalar_one_or_none()
                        if not wf:
                            continue
                        
                        definition = wf.definition or {}
                        blocks = {b['id']: b for b in definition.get('blocks', [])}
                        paused_block_id = exec_rec.current_block_id
                        wait_block = blocks.get(paused_block_id, {})
                        timeout_seconds = int(wait_block.get('config', {}).get('timeout_seconds', 7200))
                        
                        # Determine base time
                        base_time = getattr(exec_rec, 'updated_at', None) or exec_rec.started_at or exec_rec.created_at
                        if not base_time:
                            continue
                        if base_time.tzinfo is None:
                            base_time = base_time.replace(tzinfo=timezone.utc)
                        
                        elapsed = (now - base_time).total_seconds()
                        if elapsed >= timeout_seconds:
                            logger.info(
                                f"[WorkflowScheduler] ⏰ Workflow execution {exec_rec.id} (Workflow '{wf.name}') "
                                f"timed out after {elapsed:.1f}s (limit: {timeout_seconds}s)"
                            )
                            
                            engine = WorkflowEngine(db)
                            strict_cfg = engine._get_strict_config(wf)
                            timeout_msg = (
                                strict_cfg.get('strict_timeout_message') or
                                "Tempo limite de resposta esgotado. O atendimento foi encerrado."
                            )
                            
                            exec_rec.status = "timed_out"
                            exec_rec.error_message = f"Execution timed out after {timeout_seconds} seconds"
                            exec_rec.completed_at = now
                            await db.commit()
                            
                            context = exec_rec.context or {}
                            trigger_payload = (
                                context.get('$trigger', {}).get('payload', {})
                                if isinstance(context.get('$trigger'), dict)
                                else context.get('trigger', {}).get('payload', {})
                            )
                            session_id = None
                            if isinstance(trigger_payload, dict):
                                session_id = trigger_payload.get('session_id')
                            if not session_id and isinstance(context.get('session_id'), str):
                                session_id = context.get('session_id')
                                
                            if session_id:
                                from app.redis_client import redis_client
                                try:
                                    curr_active = await redis_client.get(f"active_workflow_run:{session_id}")
                                    if curr_active == str(exec_rec.id):
                                        await redis_client.delete(f"active_workflow_run:{session_id}")
                                except Exception as r_err:
                                    logger.debug(f"[WorkflowScheduler] Could not delete active_workflow_run key: {r_err}")
                                
                                try:
                                    # Save to Redis & MTM
                                    await redis_client.add_message(
                                        session_id=session_id, role="assistant", content=timeout_msg, ttl_seconds=86400
                                    )
                                    from app.worker.tasks import _save_mtm_message
                                    import uuid as _uuid
                                    agent_id = trigger_payload.get('agent_id') if isinstance(trigger_payload, dict) else None
                                    _save_agent_id = agent_id or str(_uuid.UUID(int=0))
                                    await _save_mtm_message(db, _save_agent_id, session_id, "assistant", timeout_msg)
                                except Exception as mtm_err:
                                    logger.debug(f"[WorkflowScheduler] Could not save timeout message to MTM: {mtm_err}")
                                
                                # Send proactive notification via callback / egress
                                callback_url = None
                                if isinstance(trigger_payload, dict):
                                    callback_url = trigger_payload.get('callback_url')
                                if not callback_url:
                                    callback_url = context.get('callback_url') or (context.get('$request', {}) or {}).get('callback_url')
                                    
                                response_data = {
                                    "status": "timed_out",
                                    "execution_id": str(exec_rec.id),
                                    "workflow_name": wf.name,
                                    "response": timeout_msg,
                                    "message": timeout_msg,
                                    "is_hitl_pause": False,
                                }
                                transition_data = (
                                    trigger_payload.get('transition_data')
                                    if isinstance(trigger_payload, dict)
                                    else None
                                ) or context.get('transition_data')
                                if transition_data:
                                    response_data["transition_data"] = transition_data
                                    
                                if callback_url:
                                    try:
                                        from app.worker.tasks import _send_callback
                                        await _send_callback(callback_url, response_data)
                                        logger.info(f"[WorkflowScheduler] 📤 Dispatched timeout notification to {callback_url}")
                                    except Exception as cb_err:
                                        logger.error(f"[WorkflowScheduler] Failed to dispatch callback for timeout: {cb_err}")
                    except Exception as exec_proc_err:
                        logger.error(f"[WorkflowScheduler] Error checking timeout for execution {exec_rec.id}: {exec_proc_err}")
            except Exception as outer_err:
                logger.error(f"[WorkflowScheduler] Error in check_workflow_timeouts: {outer_err}")

    async def sync_workflow(self, workflow_id: UUID, is_active: bool, definition: dict):
        """Sync a single workflow schedule with the running scheduler."""
        job_id = str(workflow_id)
        
        # Remove existing job if any
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info(f"[WorkflowScheduler] Removed job for workflow {workflow_id}")

        if not is_active:
            return

        # Find schedule trigger block
        blocks = definition.get("blocks", [])
        # definition can be a list or dict depending on parsing, but normalized structure:
        # definition.blocks is a list in v2
        if isinstance(blocks, list):
            for block in blocks:
                if block.get("type") == "trigger":
                    config = block.get("config", {})
                    if config.get("trigger_type") == "schedule" and config.get("cron"):
                        cron_expr = config.get("cron")
                        try:
                            trigger = CronTrigger.from_crontab(cron_expr)
                            self.scheduler.add_job(
                                func=self.run_scheduled_workflow,
                                trigger=trigger,
                                args=[workflow_id],
                                id=job_id,
                                replace_existing=True
                            )
                            logger.info(f"[WorkflowScheduler] Scheduled workflow {workflow_id} with cron: {cron_expr}")
                        except Exception as e:
                            logger.error(f"[WorkflowScheduler] Failed to parse cron expression '{cron_expr}' for workflow {workflow_id}: {e}")
        elif isinstance(blocks, dict):
            for block in blocks.values():
                if block.get("type") == "trigger":
                    config = block.get("config", {})
                    if config.get("trigger_type") == "schedule" and config.get("cron"):
                        cron_expr = config.get("cron")
                        try:
                            trigger = CronTrigger.from_crontab(cron_expr)
                            self.scheduler.add_job(
                                func=self.run_scheduled_workflow,
                                trigger=trigger,
                                args=[workflow_id],
                                id=job_id,
                                replace_existing=True
                            )
                            logger.info(f"[WorkflowScheduler] Scheduled workflow {workflow_id} with cron: {cron_expr}")
                        except Exception as e:
                            logger.error(f"[WorkflowScheduler] Failed to parse cron expression '{cron_expr}' for workflow {workflow_id}: {e}")

    async def sync_all_workflows(self):
        """Sync all active workflows from the database."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Workflow).where(Workflow.is_active == True))
            workflows = result.scalars().all()
            
            for wf in workflows:
                await self.sync_workflow(wf.id, wf.is_active, wf.definition or {})

    async def run_scheduled_workflow(self, workflow_id: UUID):
        """Executed by the scheduler to run a workflow."""
        logger.info(f"[WorkflowScheduler] Triggering scheduled workflow: {workflow_id}")
        async with AsyncSessionLocal() as db:
            # Validate workflow is still active
            result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
            wf = result.scalar_one_or_none()
            if not wf or not wf.is_active:
                job_id = str(workflow_id)
                if self.scheduler.get_job(job_id):
                    self.scheduler.remove_job(job_id)
                return

            engine = WorkflowEngine(db)
            try:
                await engine.execute(
                    workflow_id=workflow_id,
                    trigger_data={"scheduled": True},
                    trigger_type="schedule"
                )
                logger.info(f"[WorkflowScheduler] Scheduled workflow {workflow_id} executed successfully.")
            except Exception as e:
                logger.error(f"[WorkflowScheduler] Error executing scheduled workflow {workflow_id}: {e}")

# Global instance
workflow_scheduler = WorkflowScheduler()
