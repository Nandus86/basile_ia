"""
Migration: Add strict_mode, strict_fallback_message, and strict_exit_keywords columns to workflows table.

These columns allow a workflow to lock the conversation in strict mode,
blocking AI agent execution and providing fallback retry prompts.
"""
import asyncio
from sqlalchemy import text
from app.database import engine


async def run_migration():
    async with engine.begin() as conn:
        print("Checking/adding strict mode columns to 'workflows' table...")

        # 1. strict_mode
        check_strict = await conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name='workflows' AND column_name='strict_mode';
        """))
        if check_strict.fetchone():
            print("Column 'strict_mode' already exists.")
        else:
            await conn.execute(text(
                "ALTER TABLE workflows ADD COLUMN strict_mode BOOLEAN NOT NULL DEFAULT FALSE;"
            ))
            print("Column 'strict_mode' added successfully.")

        # 2. strict_fallback_message
        check_fb = await conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name='workflows' AND column_name='strict_fallback_message';
        """))
        if check_fb.fetchone():
            print("Column 'strict_fallback_message' already exists.")
        else:
            await conn.execute(text(
                "ALTER TABLE workflows ADD COLUMN strict_fallback_message TEXT NULL;"
            ))
            print("Column 'strict_fallback_message' added successfully.")

        # 3. strict_exit_keywords
        check_exit = await conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name='workflows' AND column_name='strict_exit_keywords';
        """))
        if check_exit.fetchone():
            print("Column 'strict_exit_keywords' already exists.")
        else:
            await conn.execute(text(
                "ALTER TABLE workflows ADD COLUMN strict_exit_keywords JSON DEFAULT '[\"sair\", \"cancelar\", \"menu\", \"parar\", \"encerrar\"]'::json;"
            ))
            print("Column 'strict_exit_keywords' added successfully.")

        print("Migration for strict_mode columns completed successfully.")


if __name__ == "__main__":
    asyncio.run(run_migration())
