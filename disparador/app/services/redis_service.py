import json
import logging
from redis.asyncio import Redis, ConnectionPool
import random
from typing import Optional, List, Dict
from datetime import datetime, timezone

from app.config import settings

logger = logging.getLogger(__name__)

class DisparadorRedis:
    def __init__(self):
        self.url = settings.REDIS_URL
        self.pool = None
        self.client: Redis = None

    async def connect(self):
        if not self.pool:
            self.pool = ConnectionPool.from_url(
                self.url,
                decode_responses=True,
                max_connections=50
            )
            self.client = Redis(connection_pool=self.pool)
            logger.info("Connected to Redis for Disparador.")

    async def disconnect(self):
        if self.client:
            await self.client.close()
            if self.pool:
                await self.pool.disconnect()
            logger.info("Disconnected from Redis for Disparador.")

    async def ensure_connected(self):
        if not self.client:
            await self.connect()

    # -- Config Cache --
    async def cache_config(self, path: str, config_dict: dict, ttl: int = 300):
        await self.ensure_connected()
        key = f"disp:config:{path}"
        await self.client.set(key, json.dumps(config_dict), ex=ttl)

    async def get_cached_config(self, path: str) -> Optional[dict]:
        await self.ensure_connected()
        key = f"disp:config:{path}"
        data = await self.client.get(key)
        if data:
            return json.loads(data)
        return None

    # -- Index Fisher-Yates --
    async def get_next_index(self, config_id: str, service_id: str, index_max: int) -> int:
        await self.ensure_connected()
        key = f"disp:index:{config_id}:{service_id}"
        
        raw = await self.client.get(key)
        if raw:
            state = json.loads(raw)
            remaining = state.get("remaining", [])
        else:
            remaining = []
            
        if not remaining:
            remaining = list(range(index_max + 1))
            random.shuffle(remaining)
            
        chosen = remaining.pop(0)
        await self.client.set(key, json.dumps({
            "remaining": remaining, 
            "max": index_max
        }))
        return chosen

    # -- Campaign Tracking --
    async def init_campaign(self, service_id: str, total: int, config_id: str, config_path: str, campaign_key: str = None):
        await self.ensure_connected()
        key = f"disp:campaign:{service_id}"
        # Only init if not exists to support resuming
        exists = await self.client.exists(key)
        if not exists:
            data = {
                "status": "running",
                "total": total,
                "sent": 0,
                "failed": 0,
                "percent": 0.0,
                "config_id": config_id,
                "config_path": config_path,
                "campaign_key": campaign_key,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "completed_at": None
            }
            await self.client.set(key, json.dumps(data))

    async def get_campaign(self, service_id: str) -> Optional[dict]:
        await self.ensure_connected()
        key = f"disp:campaign:{service_id}"
        data = await self.client.get(key)
        if data:
            return json.loads(data)
        return None

    async def _update_campaign_counter(self, service_id: str, field: str):
        await self.ensure_connected()
        key = f"disp:campaign:{service_id}"
        data = await self.get_campaign(service_id)
        if data:
            data[field] = data.get(field, 0) + 1
            if data["total"] > 0:
                data["percent"] = round((data["sent"] + data["failed"]) / data["total"] * 100, 2)
            await self.client.set(key, json.dumps(data))
            
    async def get_sent_count(self, service_id: str) -> int:
        data = await self.get_campaign(service_id)
        return data.get("sent", 0) if data else 0

    async def increment_sent(self, service_id: str):
        await self._update_campaign_counter(service_id, "sent")

    async def increment_failed(self, service_id: str):
        await self._update_campaign_counter(service_id, "failed")

    async def complete_campaign(self, service_id: str):
        await self.ensure_connected()
        key = f"disp:campaign:{service_id}"
        data = await self.get_campaign(service_id)
        if data:
            data["status"] = "completed"
            data["completed_at"] = datetime.now(timezone.utc).isoformat()
            data["percent"] = 100.0
            await self.client.set(key, json.dumps(data))

    async def list_campaigns(self, status: str = None) -> List[dict]:
        await self.ensure_connected()
        campaigns = []
        async for key in self.client.scan_iter("disp:campaign:*"):
            # Keep only campaign payload keys: disp:campaign:{service_id}
            key_parts = key.split(":")
            if len(key_parts) != 3:
                continue

            data = await self.client.get(key)
            if not data:
                continue

            try:
                c = json.loads(data)
            except json.JSONDecodeError:
                logger.warning("Skipping non-JSON campaign key '%s'", key)
                continue

            c["service_id"] = key_parts[-1]
            if not status or c.get("status") == status:
                campaigns.append(c)

        return sorted(campaigns, key=lambda x: x.get("started_at", ""), reverse=True)

    # -- Pause --
    async def pause_campaign(self, service_id: str):
        await self.ensure_connected()
        await self.client.set(f"disp:paused:{service_id}", "paused")
        # Update status
        key = f"disp:campaign:{service_id}"
        data = await self.get_campaign(service_id)
        if data and data.get("status") == "running":
            data["status"] = "paused"
            await self.client.set(key, json.dumps(data))

    async def resume_campaign(self, service_id: str):
        await self.ensure_connected()
        await self.client.delete(f"disp:paused:{service_id}")
        # Update status
        key = f"disp:campaign:{service_id}"
        data = await self.get_campaign(service_id)
        if data and data.get("status") == "paused":
            data["status"] = "running"
            await self.client.set(key, json.dumps(data))

    async def is_paused(self, service_id: str) -> bool:
        await self.ensure_connected()
        return await self.client.exists(f"disp:paused:{service_id}") == 1

    # -- DLQ --
    async def add_to_dlq(self, service_id: str, contact: dict, error: str, attempts: int = 1):
        await self.ensure_connected()
        item = {
            "contact": contact,
            "error": error,
            "attempts": attempts,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.client.rpush(f"disp:dlq:{service_id}", json.dumps(item))

    async def get_dlq(self, service_id: str) -> List[dict]:
        await self.ensure_connected()
        items = await self.client.lrange(f"disp:dlq:{service_id}", 0, -1)
        return [json.loads(i) for i in items] if items else []

    async def clear_dlq(self, service_id: str):
        await self.ensure_connected()
        await self.client.delete(f"disp:dlq:{service_id}")

    # -- Rate Limiting --
    async def check_rate_limit(self, number: str, cooldown_seconds: int = 300) -> bool:
        """Returns True if allowed, False if blocked"""
        await self.ensure_connected()
        key = f"disp:rate:{number}"
        # set nx (only if not exists), ex (expire)
        result = await self.client.set(key, "1", nx=True, ex=cooldown_seconds)
        return result is True

    # -- Campaign Lock (Business Rule) --
    async def get_campaign_lock(self, campaign_key: str) -> str:
        await self.ensure_connected()
        key = f"disp:campaign:lock:{campaign_key}"
        value = await self.client.get(key)
        return value or "unlocked"

    async def is_campaign_locked(self, campaign_key: str) -> bool:
        return await self.get_campaign_lock(campaign_key) == "locked"

    async def lock_campaign(self, campaign_key: str):
        await self.ensure_connected()
        await self.client.set(f"disp:campaign:lock:{campaign_key}", "locked")

    async def unlock_campaign(self, campaign_key: str):
        await self.ensure_connected()
        await self.client.set(f"disp:campaign:lock:{campaign_key}", "unlocked")

    # -- Run Status (Technical State) --
    async def get_run_status(self, run_id: str) -> Optional[str]:
        await self.ensure_connected()
        return await self.client.get(f"disp:run:status:{run_id}")

    async def set_run_status(self, run_id: str, status: str, ttl: int = 86400):
        await self.ensure_connected()
        await self.client.set(f"disp:run:status:{run_id}", status, ex=ttl)

    async def delete_run_status(self, run_id: str):
        await self.ensure_connected()
        await self.client.delete(f"disp:run:status:{run_id}")

    async def set_last_run(self, campaign_key: str, run_id: str):
        await self.ensure_connected()
        await self.client.set(f"disp:campaign:last_run:{campaign_key}", run_id)

    async def get_last_run(self, campaign_key: str) -> Optional[str]:
        await self.ensure_connected()
        return await self.client.get(f"disp:campaign:last_run:{campaign_key}")

    async def signal_cancel(self, run_id: str):
        await self.ensure_connected()
        channel = f"disp:cancel-chan:{run_id}"
        await self.client.publish(channel, "cancel")

disparador_redis = DisparadorRedis()

