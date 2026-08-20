"""
Migration script to add auto_dispatch_mapping column to analytics_config table.
"""
import asyncio
from sqlalchemy import text
from app.database import engine

async def run_migration():
    print("Running migration: Adding auto_dispatch_mapping to analytics_config...")
    async with engine.begin() as conn:
        await conn.execute(text("""
            ALTER TABLE analytics_config 
            ADD COLUMN IF NOT EXISTS auto_dispatch_mapping JSONB DEFAULT '[]'::jsonb;
            
            UPDATE analytics_config
            SET auto_dispatch_mapping = '[]'::jsonb
            WHERE auto_dispatch_mapping IS NULL;
        """))
    print("Migration completed successfully!")

if __name__ == "__main__":
    asyncio.run(run_migration())
