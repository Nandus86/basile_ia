"""
Background Dispatcher - Retries queued messages that failed to forward
"""
import asyncio
import json
import logging
from datetime import datetime, timezone

from app.config import settings
from app.redis_client import redis_client
from app.services.http_forwarder import forwarder

logger = logging.getLogger("basile-ingress.dispatcher")

QUEUE_PREFIX = "pipeline:queue"
STATUS_PREFIX = "pipeline:status"


class Dispatcher:
    def __init__(self):
        self.running = False
        self.interval = settings.DISPATCH_INTERVAL_SECONDS
        self.max_retries = settings.DISPATCH_MAX_RETRIES

    async def start(self):
        """Start the dispatcher background loop"""
        self.running = True
        logger.info(
            f"[Dispatcher] Started — interval={self.interval}s, max_retries={self.max_retries}"
        )
        while self.running:
            try:
                await self._process_all_queues()
            except Exception as e:
                logger.error(f"[Dispatcher] Cycle error: {e}")
            await asyncio.sleep(self.interval)

    async def stop(self):
        self.running = False
        logger.info("[Dispatcher] Stopped")

    # ── internal ──

    async def _process_all_queues(self):
        client = await redis_client.connect()
        keys = []
        async for key in client.scan_iter(match=f"{QUEUE_PREFIX}:*", count=100):
            keys.append(key)

        for queue_key in keys:
            await self._process_one(queue_key)

    async def _process_one(self, queue_key: str):
        raw = await redis_client.pop_from_queue(queue_key)
        if not raw:
            return

        try:
            job_data = json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f"[Dispatcher] Bad JSON in {queue_key}, dropping")
            return

        job_id = job_data.get("job_id", "unknown")
        output_url = job_data.get("_forward_url")
        output_method = job_data.get("_forward_method", "POST")
        retry_count = job_data.get("_retry_count", 0)

        if not output_url:
            logger.error(f"[Dispatcher] Job {job_id} has no _forward_url, dropping")
            await self._set_status(job_id, "failed", error="No forward URL")
            return

        worker_payload = self._extract_worker_payload(job_data)

        success, response_data, error = await forwarder.forward(
            output_url, worker_payload, output_method
        )

        if success:
            logger.info(f"[Dispatcher] ✅ Job {job_id} forwarded (attempt {retry_count + 1})")
            await self._set_status(job_id, "forwarded", attempts=retry_count + 1)
            if response_data:
                await redis_client.set(
                    f"pipeline:response:{job_id}",
                    json.dumps(response_data, default=str),
                    expire=86400,
                )
        else:
            retry_count += 1
            if retry_count >= self.max_retries:
                logger.error(
                    f"[Dispatcher] ❌ Job {job_id} exhausted {retry_count} retries: {error}"
                )
                await self._set_status(
                    job_id, "failed", attempts=retry_count, error=error
                )
            else:
                job_data["_retry_count"] = retry_count
                logger.warning(
                    f"[Dispatcher] ⏳ Job {job_id} retry {retry_count}: {error}"
                )
                await self._set_status(
                    job_id, f"retry_{retry_count}", attempts=retry_count, error=error
                )
                await redis_client.push_to_queue(
                    queue_key, json.dumps(job_data, default=str), ttl=86400
                )

    @staticmethod
    def _extract_worker_payload(job_data: dict) -> dict:
        """Build payload compatible with /webhook/process"""
        payload = {
            "message": job_data.get("message", ""),
            "session_id": job_data.get("session_id", ""),
        }
        for key in (
            "agent_id", "user_access_level", "context_data",
            "transition_data", "callback_url",
        ):
            val = job_data.get(key)
            if val is not None:
                payload[key] = val
        return payload

    async def _set_status(
        self, job_id: str, status: str, attempts: int = 0, error: str = None
    ):
        await redis_client.set(
            f"{STATUS_PREFIX}:{job_id}",
            json.dumps({
                "job_id": job_id,
                "status": status,
                "attempts": attempts,
                "last_error": error,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }),
            expire=86400,
        )


dispatcher = Dispatcher()
