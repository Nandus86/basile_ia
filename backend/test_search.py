import asyncio
from app.database import engine
from sqlalchemy import text

async def test_search():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT count(*) FROM job_logs WHERE session_id IS NOT NULL"))
        print(f"Total records with session_id: {result.scalar()}")
        
        result = await conn.execute(text("SELECT session_id FROM job_logs WHERE session_id ILIKE '%4670%' LIMIT 5"))
        print("Records containing '4670':")
        for row in result:
            print(row[0])

asyncio.run(test_search())
