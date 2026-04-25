"""
Redis Client for basile-ingress
"""
import redis.asyncio as redis
from typing import Optional

from app.config import settings


class RedisClient:
    def __init__(self):
        self.client: Optional[redis.Redis] = None
    
    async def connect(self):
        if not self.client:
            self.client = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50
            )
        return self.client
    
    async def disconnect(self):
        if self.client:
            await self.client.close()
            self.client = None
    
    async def ping(self) -> bool:
        try:
            client = await self.connect()
            await client.ping()
            return True
        except Exception:
            return False
    
    async def push_to_queue(self, queue_key: str, data: str, ttl: int = 86400):
        client = await self.connect()
        await client.rpush(queue_key, data)
        await client.expire(queue_key, ttl)
    
    async def pop_from_queue(self, queue_key: str) -> Optional[str]:
        client = await self.connect()
        return await client.lpop(queue_key)
    
    async def set(self, key: str, value: str, expire: int = None):
        client = await self.connect()
        if expire:
            await client.setex(key, expire, value)
        else:
            await client.set(key, value)
    
    async def get(self, key: str) -> Optional[str]:
        client = await self.connect()
        return await client.get(key)
    
    async def delete(self, key: str):
        client = await self.connect()
        await client.delete(key)


redis_client = RedisClient()


async def get_redis() -> RedisClient:
    return redis_client