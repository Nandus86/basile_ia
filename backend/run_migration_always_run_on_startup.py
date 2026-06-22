import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://postgres:postgres@localhost:5432/basile_db"
)

async def run_migration():
    engine = create_async_engine(DATABASE_URL)
    
    with open("migrations/add_always_run_on_startup.sql", "r", encoding="utf-8") as f:
        sql = f.read()
        
    try:
        async with engine.begin() as conn:
            from sqlalchemy import text
            await conn.execute(text(sql))
            print("Migração executada com sucesso!")
    except Exception as e:
        print(f"Erro ao executar migração: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run_migration())
