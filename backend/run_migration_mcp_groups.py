import asyncio
import os
import sys
from sqlalchemy import text

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.database import engine

async def run_migration():
    migration_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations", "add_mcp_groups.sql")
    print(f"Reading migration file: {migration_file}")
    
    with open(migration_file, "r", encoding="utf-8") as f:
        sql_content = f.read()

    # Split by double newline instead, or just pass full content? 
    # Let's clean up starting comments
    clean_sqls = []
    for stmt in sql_content.split(';'):
        stmt = stmt.strip()
        if not stmt:
            continue
        # If it starts with a comment, it might be fine, but let's send it
        clean_sqls.append(stmt)
        
    statements = clean_sqls

    print("Connecting to database...")
    try:
        async with engine.begin() as conn:
            for statement in statements:
                print(f"Executing SQL: {statement[:50]}...")
                await conn.execute(text(statement))
            
        print("\n✅ Migration 'add_mcp_groups.sql' executed successfully!")
    except Exception as e:
        print(f"\n❌ Error executing migration: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_migration())
