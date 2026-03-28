import asyncio
from app.database import AsyncSessionLocal
from sqlalchemy import select
from app.models.agent import Agent

async def list_agents():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Agent))
        agents = result.scalars().all()
        for a in agents:
            print(f"ID: {a.id} | Name: {a.name} | VM: {a.vector_memory_enabled} | ORCH: {a.is_orchestrator}")

if __name__ == "__main__":
    asyncio.run(list_agents())
