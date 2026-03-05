import asyncio
import os
import sys
from sqlalchemy import text

# Add current directory to path to allow importing app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import engine

async def run_migration():
    """
    Executes the SQL migration to add the vector_memory_enabled column.
    Handles multiple statements by splitting on semicolons.
    """
    # Path to the SQL file
    migration_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations", "add_vector_memory_enabled.sql")
    
    print(f"Reading migration file: {migration_file}")
    
    if not os.path.exists(migration_file):
        print(f"ERROR: File not found: {migration_file}")
        return

    # Read SQL file
    with open(migration_file, "r", encoding="utf-8") as f:
        sql_content = f.read()

    # Split into individual statements
    statements = [s.strip() for s in sql_content.split(';') if s.strip()]

    print(f"Found {len(statements)} statements to execute.")
    print("Connecting to database...")
    
    try:
        async with engine.begin() as conn:
            for i, statement in enumerate(statements):
                # Skip comments-only statements if any
                if statement.startswith('--') and '\n' not in statement:
                    continue
                    
                print(f"Executing statement {i+1}...")
                print(f"SQL: {statement[:100]}...")  # Print first 100 chars
                
                await conn.execute(text(statement))
            
        print("\n✅ Migration executed successfully!")
        print("Column 'vector_memory_enabled' added to 'agents' table.")
        
    except Exception as e:
        print(f"\n❌ Error executing migration: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    asyncio.run(run_migration())
