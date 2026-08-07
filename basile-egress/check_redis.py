import asyncio
import json
from app.redis_client import redis_client

async def main():
    await redis_client.connect()
    client = redis_client.client
    keys = []
    async for key in client.scan_iter(match="result:status:*", count=50):
        keys.append(key)
    
    print(f"Found {len(keys)} keys")
    if keys:
        for key in keys[:5]:
            status = await redis_client.hget(key, "status")
            inp = await redis_client.hget(key, "input_payload")
            outp = await redis_client.hget(key, "output_payload")
            print(f"Key: {key}")
            print(f"  Status: {status}")
            print(f"  Has Input: {inp is not None}")
            print(f"  Has Output: {outp is not None}")
    
    await redis_client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
