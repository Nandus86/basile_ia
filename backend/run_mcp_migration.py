import asyncio
from sqlalchemy import text
from app.database import engine

async def migrate():
    async with engine.begin() as conn:
        print("Adding always_run_on_startup to mcps table...")
        await conn.execute(text("ALTER TABLE mcps ADD COLUMN IF NOT EXISTS always_run_on_startup BOOLEAN DEFAULT FALSE;"))
        print("Done.")

if __name__ == "__main__":
    asyncio.run(migrate())
