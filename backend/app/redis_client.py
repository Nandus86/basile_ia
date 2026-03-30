"""
Redis Client for caching and session management
"""
import redis.asyncio as redis
from typing import Optional, List
import json

from app.config import settings


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
    
    async def add_message(self, session_id: str, role: str, content: str, ttl_seconds: int = 86400):
        """Add message to conversation history with configurable TTL"""
        from datetime import datetime, timezone
        client = await self.connect()
        key = f"conversation:{session_id}"
        message = json.dumps({
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat()
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
    ):
        """Save agent session context for continuity across interactions."""
        from datetime import datetime, timezone

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
            "updated_at": datetime.now(timezone.utc).isoformat(),
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

    async def push_to_buffer(self, session_id: str, data_json: str):
        """Push a message payload to the session's pending buffer (FIFO list)."""
        client = await self.connect()
        key = f"msg_buffer:{session_id}"
        await client.rpush(key, data_json)
        await client.expire(key, 7200)  # 2h safety TTL

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


# Global instance
redis_client = RedisClient()


async def get_redis() -> RedisClient:
    """Dependency for getting Redis client"""
    return redis_client
