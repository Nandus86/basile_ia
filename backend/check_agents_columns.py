import asyncio
from sqlalchemy import text
from app.database import engine

async def check_columns():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='agents'"))
        columns = [r[0] for r in result.all()]
        print("Columns in 'agents' table:")
        for col in columns:
            print(f"- {col}")

if __name__ == "__main__":
    asyncio.run(check_columns())
