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

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("[WorkflowScheduler] Scheduler shut down successfully.")

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
