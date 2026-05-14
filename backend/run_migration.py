import asyncio
from app.database import engine
from sqlalchemy import text

async def run():
    async with engine.begin() as conn:
        await conn.execute(text('ALTER TABLE agents ADD COLUMN IF NOT EXISTS bypass_llm BOOLEAN NOT NULL DEFAULT FALSE;'))
        print('OK')

asyncio.run(run())
