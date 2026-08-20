"""
Migration: Add fallback_static_message column to agent_configs table.
"""
import asyncio
from sqlalchemy import text
from app.database import engine


async def run_migration():
    async with engine.begin() as conn:
        print("Checking/adding fallback_static_message column to 'agent_configs' table...")

        check_column = await conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name='agent_configs' AND column_name='fallback_static_message';
        """))
        if check_column.fetchone():
            print("Column 'fallback_static_message' already exists in 'agent_configs'.")
        else:
            await conn.execute(text(
                "ALTER TABLE agent_configs ADD COLUMN fallback_static_message TEXT NULL;"
            ))
            print("Column 'fallback_static_message' added successfully to 'agent_configs'.")

    await engine.dispose()
    print("Migration finished.")


if __name__ == "__main__":
    asyncio.run(run_migration())
