"""
Migration: Add return_direct_payload column to workflows table.

This column controls whether a workflow's results bypass the LLM
and are merged directly into the API response payload.
"""
import asyncio
from sqlalchemy import text
from app.database import engine


async def run_migration():
    async with engine.begin() as conn:
        # Check if column already exists
        check_result = await conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name='workflows' AND column_name='return_direct_payload';
        """))
        exists = check_result.fetchone()

        if exists:
            print("Column 'return_direct_payload' already exists in 'workflows' table.")
        else:
            print("Adding 'return_direct_payload' column to 'workflows' table...")
            await conn.execute(text(
                "ALTER TABLE workflows ADD COLUMN return_direct_payload BOOLEAN NOT NULL DEFAULT FALSE;"
            ))
            print("Column 'return_direct_payload' added successfully")


if __name__ == "__main__":
    asyncio.run(run_migration())
