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
            # Check if column exists
            check_sql = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='dispatcher_configs' AND column_name='target_endpoint';
            """)
            result = await conn.execute(check_sql)
            exists = result.scalar() is not None
            
            if exists:
                print("Column 'target_endpoint' already exists in 'dispatcher_configs' table.")
            else:
                print("Adding 'target_endpoint' column to 'dispatcher_configs' table...")
                # Add column
                await conn.execute(text("ALTER TABLE dispatcher_configs ADD COLUMN target_endpoint VARCHAR(500);"))
                print("Migration executed successfully!")
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
