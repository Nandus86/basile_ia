import asyncio
from redis.asyncio import Redis

async def test_scan():
    client = Redis(host="localhost", port=6480, decode_responses=True)
    try:
        keys = []
        cursor = b'0'
        while cursor:
            cursor, partial_keys = await client.scan(cursor, match="*", count=100)
            keys.extend(partial_keys)
            if not cursor or cursor == b'0' or cursor == 0 or cursor == '0':
                break
        print(f"Success! Found {len(keys)} keys")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_scan())
