import asyncio
import os
import sys
from sqlalchemy import text

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import engine


async def run_migration():
    print("Running Thinker migration...")
    try:
        async with engine.begin() as conn:
            # 1. Check and add is_thinker column
            check_is_thinker = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='agents' AND column_name='is_thinker';
            """)
            result = await conn.execute(check_is_thinker)
            exists = result.scalar() is not None
            
            if exists:
                print("Column 'is_thinker' already exists in 'agents' table.")
            else:
                print("Adding 'is_thinker' column to 'agents' table...")
                await conn.execute(text("ALTER TABLE agents ADD COLUMN is_thinker BOOLEAN DEFAULT FALSE NOT NULL;"))
                print("✅ Column 'is_thinker' added")
            
            # 2. Check and add thinker_prompt column
            check_thinker_prompt = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='agents' AND column_name='thinker_prompt';
            """)
            result = await conn.execute(check_thinker_prompt)
            exists = result.scalar() is not None
            
            if exists:
                print("Column 'thinker_prompt' already exists.")
            else:
                print("Adding 'thinker_prompt' column to 'agents' table...")
                await conn.execute(text("ALTER TABLE agents ADD COLUMN thinker_prompt TEXT;"))
                print("✅ Column 'thinker_prompt' added")
            
            # 3. Check and add thinker_model column
            check_thinker_model = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='agents' AND column_name='thinker_model';
            """)
            result = await conn.execute(check_thinker_model)
            exists = result.scalar() is not None
            
            if exists:
                print("Column 'thinker_model' already exists.")
            else:
                print("Adding 'thinker_model' column to 'agents' table...")
                await conn.execute(text("ALTER TABLE agents ADD COLUMN thinker_model VARCHAR(100);"))
                print("✅ Column 'thinker_model' added")
            
            # 4. Check and create agent_thinker_links table
            check_table = text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name='agent_thinker_links';
            """)
            result = await conn.execute(check_table)
            exists = result.scalar() is not None
            
            if exists:
                print("Table 'agent_thinker_links' already exists.")
            else:
                print("Creating 'agent_thinker_links' table...")
                await conn.execute(text("""
                    CREATE TABLE agent_thinker_links (
                        agent_id UUID NOT NULL,
                        thinker_id UUID NOT NULL,
                        is_active BOOLEAN DEFAULT TRUE NOT NULL,
                        PRIMARY KEY (agent_id, thinker_id),
                        FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE,
                        FOREIGN KEY (thinker_id) REFERENCES agents(id) ON DELETE CASCADE
                    );
                """))
                print("✅ Table 'agent_thinker_links' created")
            
            print("\n✅ Thinker migration completed successfully!")
    except Exception as e:
        print(f"\n❌ Error executing migration: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_migration())