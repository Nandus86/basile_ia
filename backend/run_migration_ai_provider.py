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
                WHERE table_name='agents' AND column_name='provider_id';
            """)
            result = await conn.execute(check_sql)
            exists = result.scalar() is not None
            
            if exists:
                print("Column 'provider_id' already exists in 'agents' table.")
            else:
                print("Adding 'provider_id' column to 'agents' table...")
                # Add column
                await conn.execute(text("ALTER TABLE agents ADD COLUMN provider_id UUID;"))
                # Add foreign key constraint
                await conn.execute(text("""
                    ALTER TABLE agents 
                    ADD CONSTRAINT fk_agent_provider 
                    FOREIGN KEY (provider_id) 
                    REFERENCES ai_providers(id) 
                    ON DELETE SET NULL;
                """))
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
