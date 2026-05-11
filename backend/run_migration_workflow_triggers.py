import asyncio
import os
import sys
from sqlalchemy import text

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import engine


async def run_migration():
    print("Running Workflow Trigger Keywords migration...")
    try:
        async with engine.begin() as conn:
            # 1. Check and add trigger_keywords column
            check_keywords = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='workflows' AND column_name='trigger_keywords';
            """)
            result = await conn.execute(check_keywords)
            exists = result.scalar() is not None
            
            if exists:
                print("Column 'trigger_keywords' already exists in 'workflows' table.")
            else:
                print("Adding 'trigger_keywords' column to 'workflows' table...")
                await conn.execute(text("ALTER TABLE workflows ADD COLUMN trigger_keywords JSON DEFAULT '[]';"))
                print("Column 'trigger_keywords' added successfully")
            
            # 2. Check and add trigger_match_mode column
            check_mode = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='workflows' AND column_name='trigger_match_mode';
            """)
            result = await conn.execute(check_mode)
            exists = result.scalar() is not None
            
            if exists:
                print("Column 'trigger_match_mode' already exists in 'workflows' table.")
            else:
                print("Adding 'trigger_match_mode' column to 'workflows' table...")
                await conn.execute(text("ALTER TABLE workflows ADD COLUMN trigger_match_mode VARCHAR(20) DEFAULT 'word' NOT NULL;"))
                print("Column 'trigger_match_mode' added successfully")
            
            print("Workflow Trigger Keywords migration completed successfully!")
    except Exception as e:
        print(f"Error executing migration: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_migration())
