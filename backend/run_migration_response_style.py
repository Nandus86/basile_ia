import asyncio
import os
import sys
from sqlalchemy import text

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import engine

async def run_migration():
    print("Connecting to database...")
    try:
        async with engine.begin() as conn:
            # Check if column exists to avoid errors on multiple runs
            check_sql = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='agents' AND column_name='response_style';
            """)
            result = await conn.execute(check_sql)
            exists = result.scalar() is not None
            
            if exists:
                print("Column 'response_style' already exists in 'agents' table.")
            else:
                print("Adding 'response_style' column to 'agents' table...")
                await conn.execute(text(
                    "ALTER TABLE agents ADD COLUMN response_style VARCHAR(20) DEFAULT 'structured' NOT NULL;"
                ))
                print("Migration executed successfully!")
    except Exception as e:
        print(f"\nError executing migration: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await engine.dispose()

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_migration())
