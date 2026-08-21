"""
Migration: Add strict_retry_message column to workflows table.
"""
import asyncio
from sqlalchemy import text
from app.database import engine

async def run_migration():
    async with engine.begin() as conn:
        print("Checking/adding strict_retry_message column to 'workflows' table...")
        check_col = await conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name='workflows' AND column_name='strict_retry_message';
        """))
        if check_col.fetchone():
            print("Column 'strict_retry_message' already exists.")
        else:
            await conn.execute(text(
                "ALTER TABLE workflows ADD COLUMN strict_retry_message TEXT DEFAULT 'Estamos com instabilidade, vamos iniciar novamente.';"
            ))
            print("Column 'strict_retry_message' added successfully.")

if __name__ == "__main__":
    asyncio.run(run_migration())
