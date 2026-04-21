"""
Migration script to add execution_mode to agents table.
Run manually:
    python run_migration_execution_mode.py
"""

import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import engine
from sqlalchemy import text


async def run():
    print("Running execution_mode migration...")
    try:
        async with engine.begin() as conn:
            # 1. Check if execution_mode enum type exists
            check_type = text("""
                SELECT 1
                FROM pg_type
                WHERE typname = 'executionmode';
            """)
            result = await conn.execute(check_type)
            type_exists = result.scalar() is not None

            if not type_exists:
                print("Creating ENUM type 'executionmode'...")
                await conn.execute(text("""
                    CREATE TYPE executionmode AS ENUM ('balanced', 'tools_first', 'orchestrator_first');
                """))
                print("[OK] ENUM type 'executionmode' created")
            else:
                print("ENUM type 'executionmode' already exists")

            # 2. Check if column exists
            check_column = text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='agents' AND column_name='execution_mode';
            """)
            result = await conn.execute(check_column)
            column_exists = result.scalar() is not None

            if column_exists:
                print("Column 'execution_mode' already exists in 'agents' table.")
            else:
                print("Adding 'execution_mode' column to 'agents' table...")
                await conn.execute(text("""
                    ALTER TABLE agents
                    ADD COLUMN execution_mode executionmode NOT NULL DEFAULT 'balanced';
                """))
                print("[OK] Column 'execution_mode' added with default 'balanced'")

            # 3. Backfill existing rows (not needed since DEFAULT covers it, but explicit for safety)
            # If any NULLs appear later, you can run:
            # UPDATE agents SET execution_mode = 'balanced' WHERE execution_mode IS NULL;

        print("[migration] execution_mode migration completed successfully.")

    except Exception as e:
        print(f"[migration] ERROR: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(run())
