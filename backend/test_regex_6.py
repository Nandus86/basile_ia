import asyncio
from app.database import engine
from sqlalchemy import text

async def list_mcps():
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT name, endpoint, query_template FROM mcps"))
        for row in result:
            print(row.name, row.query_template)

if __name__ == "__main__":
    asyncio.run(list_mcps())
