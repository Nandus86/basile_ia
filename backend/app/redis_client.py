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
    
    async def add_message(self, session_id: str, role: str, content: str):
        """Add message to conversation history"""
        client = await self.connect()
        key = f"conversation:{session_id}"
        message = json.dumps({"role": role, "content": content})
        await client.rpush(key, message)
        await client.expire(key, 86400)  # 24 hours
    
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


# Global instance
redis_client = RedisClient()


async def get_redis() -> RedisClient:
    """Dependency for getting Redis client"""
    return redis_client
