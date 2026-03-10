import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import json

DATABASE_URL = "postgresql+asyncpg://basile:basile123@basile-postgres:5432/basile_db"

async def main():
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    with open("agent_out.json", "w", encoding="utf-8") as f:
        async with async_session() as session:
            res = await session.execute(text("SELECT id, name, input_schema, output_schema, system_prompt FROM agents WHERE collaboration_enabled = true;"))
            for r in res.fetchall():
                f.write(json.dumps({
                    "id": str(r[0]), 
                    "name": r[1],
                    "input_schema": r[2], 
                    "output_schema": r[3],
                    "system_prompt": r[4][:100] + "..." if r[4] else None
                }) + "\n")

if __name__ == "__main__":
    asyncio.run(main())
