"""
Redis Client for caching and session management
"""
import redis.asyncio as redis
from typing import Optional, List, Dict, Any
import json

from app.config import settings


def _resolve_now(tz_name: str = None):
    """Return current datetime in the given IANA timezone, fallback to UTC."""
    from datetime import datetime, timezone
    if not tz_name:
        return datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        import pytz
        try:
            return datetime.now(pytz.timezone(tz_name))
        except Exception:
            return datetime.now(timezone.utc)
    try:
        return datetime.now(ZoneInfo(tz_name))
    except Exception:
        return datetime.now(timezone.utc)


class RedisClient:
    """Async Redis client wrapper"""
    
    def __init__(self):
        self.client: Optional[redis.Redis] = None
    
    async def connect(self):
        """Initialize Redis connection with connection pool"""
        if not self.client:
            self.client = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50  # Connection pool limit for concurrency
            )
        return self.client
    
    async def disconnect(self):
        """Close Redis connection"""
        if self.client:
            await self.client.close()
            self.client = None
    
    async def ping(self) -> bool:
        """Test Redis connection"""
        try:
            client = await self.connect()
            await client.ping()
            return True
        except Exception:
            return False
    
    async def set(self, key: str, value: str, expire: int = None):
        """Set a key-value pair"""
        client = await self.connect()
        if expire:
            await client.setex(key, expire, value)
        else:
            await client.set(key, value)
    
    async def get(self, key: str) -> Optional[str]:
        """Get value by key"""
        client = await self.connect()
        return await client.get(key)
    
    async def delete(self, key: str):
        """Delete a key"""
        client = await self.connect()
        await client.delete(key)
    
    async def add_message(self, session_id: str, role: str, content: str, ttl_seconds: int = 86400, tz_name: str = None):
        """Add message to conversation history with configurable TTL"""
        from datetime import datetime, timezone
        client = await self.connect()
        key = f"conversation:{session_id}"
        message = json.dumps({
            "role": role,
            "content": content,
            "timestamp": _resolve_now(tz_name).isoformat()
        })
        await client.rpush(key, message)
        await client.expire(key, ttl_seconds)
    
    async def get_conversation(self, session_id: str, limit: int = 20) -> List[dict]:
        """Get conversation history"""
        client = await self.connect()
        key = f"conversation:{session_id}"
        messages = await client.lrange(key, -limit, -1)
        return [json.loads(m) for m in messages]
    
    async def clear_conversation(self, session_id: str):
        """Clear conversation history"""
        client = await self.connect()
        key = f"conversation:{session_id}"
        await client.delete(key)

    async def save_session_context(
        self,
        session_id: str,
        agent_id: str,
        agent_name: str,
        ttl_seconds: int = 86400,
        tz_name: str = None,
    ):
        """Save agent session context for continuity across interactions."""
        client = await self.connect()
        key = f"session_context:{session_id}"

        # Load existing context to accumulate agents_used
        existing_raw = await client.get(key)
        agents_used: list = []
        if existing_raw:
            try:
                existing = json.loads(existing_raw)
                agents_used = existing.get("agents_used", [])
            except Exception:
                pass

        if agent_name not in agents_used:
            agents_used.append(agent_name)

        payload = json.dumps({
            "last_agent_id": agent_id,
            "last_agent_name": agent_name,
            "agents_used": agents_used,
            "updated_at": _resolve_now(tz_name).isoformat(),
        })
        await client.setex(key, ttl_seconds, payload)

    async def get_session_context(self, session_id: str) -> Optional[dict]:
        """Get agent session context for continuity. Returns None if not found."""
        client = await self.connect()
        key = f"session_context:{session_id}"
        raw = await client.get(key)
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                return None
        return None

    async def publish(self, channel: str, message: str):
        """Publish a message to a channel (Pub/Sub)"""
        client = await self.connect()
        await client.publish(channel, message)

    # ─── Job Concurrency Guard ───────────────────────────────

    async def acquire_user_lock(self, session_id: str, job_id: str, ttl: int = 1800) -> bool:
        """
        Attempt to acquire an exclusive lock for a session_id.
        Uses SET NX EX (atomic set-if-not-exists with expiry).
        Returns True if lock was acquired, False if another job holds it.
        """
        client = await self.connect()
        result = await client.set(
            f"user_lock:{session_id}", job_id, nx=True, ex=ttl
        )
        return result is not None

    async def release_user_lock(self, session_id: str):
        """Release the concurrency lock for a session_id."""
        client = await self.connect()
        await client.delete(f"user_lock:{session_id}")

    async def get_user_lock_owner(self, session_id: str) -> Optional[str]:
        """Return the current job_id owner of a session lock, if any."""
        client = await self.connect()
        return await client.get(f"user_lock:{session_id}")

    async def push_to_buffer(self, session_id: str, data_json: str):
        """Push a message payload to the session's pending buffer (FIFO list)."""
        client = await self.connect()
        key = f"msg_buffer:{session_id}"
        await client.rpush(key, data_json)
        await client.expire(key, 7200)  # 2h safety TTL

    async def is_job_already_buffered(self, session_id: str, original_job_id: str) -> bool:
        """Check if original_job_id already exists in session buffer payloads."""
        client = await self.connect()
        key = f"msg_buffer:{session_id}"
        items = await client.lrange(key, 0, -1)
        for item in items:
            try:
                parsed = json.loads(item)
                if not isinstance(parsed, dict):
                    continue

                if parsed.get("original_job_id") == original_job_id:
                    return True

                nested_payload = parsed.get("payload")
                if isinstance(nested_payload, dict) and nested_payload.get("original_job_id") == original_job_id:
                    return True
            except Exception:
                continue
        return False

    async def drain_buffer(self, session_id: str) -> List[str]:
        """
        Atomically read all buffered messages and clear the list.
        Uses a pipeline to ensure LRANGE + DEL are executed together.
        Returns list of JSON strings.
        """
        client = await self.connect()
        key = f"msg_buffer:{session_id}"
        pipe = client.pipeline(transaction=True)
        pipe.lrange(key, 0, -1)
        pipe.delete(key)
        results = await pipe.execute()
        return results[0] if results[0] else []

    # ─── Agent Pause (Human Takeover) ────────────────────────

    async def set_agent_pause(self, session_id: str, timeout_minutes: int = None):
        """
        Pause the agent for a session_id.
        If timeout_minutes is provided, the pause expires automatically (temporary).
        If None, the pause is permanent until manually removed (fixed).
        """
        client = await self.connect()
        key = f"agent_pause:{session_id}"
        if timeout_minutes and timeout_minutes > 0:
            await client.setex(key, timeout_minutes * 60, "paused")
        else:
            await client.set(key, "paused")

    async def is_agent_paused(self, session_id: str) -> bool:
        """Check if the agent is paused for a session_id."""
        client = await self.connect()
        return await client.exists(f"agent_pause:{session_id}") > 0

    async def remove_agent_pause(self, session_id: str):
        """Remove agent pause, reactivating it for this session_id."""
        client = await self.connect()
        await client.delete(f"agent_pause:{session_id}")

    # ─── Anti-Bot Guard ───────────────────────────────────────

    async def increment_antibot_counter(self, session_id: str) -> int:
        """Increment the anti-bot message counter for a session. Returns new count."""
        client = await self.connect()
        key = f"antibot:count:{session_id}"
        count = await client.incr(key)
        # Auto-expire counter after 24h of inactivity
        await client.expire(key, 86400)
        return count

    async def set_antibot_blocked(self, session_id: str, ttl: int = 3600):
        """Block a session flagged as bot. Default 1h TTL."""
        client = await self.connect()
        await client.setex(f"antibot:blocked:{session_id}", ttl, "blocked")

    async def is_antibot_blocked(self, session_id: str) -> bool:
        """Check if a session is currently blocked by anti-bot guard."""
        client = await self.connect()
        return await client.exists(f"antibot:blocked:{session_id}") > 0

    async def reset_antibot(self, session_id: str):
        """Clear anti-bot counter and blocked flag for a session."""
        client = await self.connect()
        pipe = client.pipeline(transaction=True)
        pipe.delete(f"antibot:count:{session_id}")
        pipe.delete(f"antibot:blocked:{session_id}")
        await pipe.execute()

    # ─── Agent-Specific Memory (Thinker Task List) ──────────────

    async def set_agent_memory(
        self,
        session_id: str,
        agent_id: str,
        memory_data: Dict[str, Any],
        ttl_seconds: int = 3600
    ):
        """
        Store agent-specific memory (Thinker task list, execution state, etc).
        Key format: agent_memory:{session_id}:{agent_id}
        This memory is NOT shared between agents - each agent has its own.
        """
        client = await self.connect()
        key = f"agent_memory:{session_id}:{agent_id}"
        value = json.dumps(memory_data, ensure_ascii=False)
        await client.setex(key, ttl_seconds, value)

    async def get_agent_memory(
        self,
        session_id: str,
        agent_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get agent-specific memory.
        Returns None if not found or expired.
        """
        client = await self.connect()
        key = f"agent_memory:{session_id}:{agent_id}"
        raw = await client.get(key)
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                return None
        return None

    async def delete_agent_memory(
        self,
        session_id: str,
        agent_id: str
    ):
        """Delete agent-specific memory."""
        client = await self.connect()
        key = f"agent_memory:{session_id}:{agent_id}"
        await client.delete(key)

    async def update_agent_memory(
        self,
        session_id: str,
        agent_id: str,
        updates: Dict[str, Any],
        ttl_seconds: int = 3600
    ) -> bool:
        """
        Update specific fields in agent memory.
        Creates new memory if doesn't exist.
        Returns True if updated, False if failed.
        """
        current = await self.get_agent_memory(session_id, agent_id)
        if current is None:
            current = {}
        
        current.update(updates)
        await self.set_agent_memory(session_id, agent_id, current, ttl_seconds)
        return True


# Global instance
redis_client = RedisClient()


async def get_redis() -> RedisClient:
    """Dependency for getting Redis client"""
    return redis_client
