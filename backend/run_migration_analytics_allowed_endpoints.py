"""
Migration script to add allowed_endpoints column to analytics_config table.
"""
import asyncio
from sqlalchemy import text
from app.database import engine

async def run_migration():
    print("Running migration: Adding allowed_endpoints to analytics_config...")
    async with engine.begin() as conn:
        await conn.execute(text("""
            ALTER TABLE analytics_config 
            ADD COLUMN IF NOT EXISTS allowed_endpoints JSONB DEFAULT '[]'::jsonb;
        """))
    print("Migration completed successfully!")

if __name__ == "__main__":
    asyncio.run(run_migration())
