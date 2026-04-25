"""
Redis Client for basile-egress
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
    
    async def hset(self, name: str, key: str, value: str):
        client = await self.connect()
        await client.hset(name, key, value)
    
    async def hget(self, name: str, key: str) -> Optional[str]:
        client = await self.connect()
        return await client.hget(name, key)
    
    async def hgetall(self, name: str) -> dict:
        client = await self.connect()
        return await client.hgetall(name)
    
    async def incr(self, key: str) -> int:
        client = await self.connect()
        return await client.incr(key)


redis_client = RedisClient()


async def get_redis() -> RedisClient:
    return redis_client