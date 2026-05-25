import asyncio
from sqlalchemy import text
from app.database import engine

async def migrate():
    print("Running Workflow return_direct_payload migration...")
    try:
        async with engine.begin() as conn:
            # Check if column exists
            check_query = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='workflows' AND column_name='return_direct_payload';
            """)
            result = await conn.execute(check_query)
            if result.fetchone() is not None:
                print("Column 'return_direct_payload' already exists in 'workflows' table.")
            else:
                print("Adding 'return_direct_payload' column to 'workflows' table...")
                await conn.execute(text("ALTER TABLE workflows ADD COLUMN return_direct_payload BOOLEAN DEFAULT FALSE;"))
                print("Column 'return_direct_payload' added successfully")
                
            print("Migration completed successfully!")
    except Exception as e:
        print(f"Migration failed: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
