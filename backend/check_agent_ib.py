import asyncio
from app.database import AsyncSessionLocal
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models.agent import Agent

async def check_agent_info_bases():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Agent).options(selectinload(Agent.information_bases))
        )
        agents = result.scalars().all()
        for a in agents:
            ib_names = [ib.name for ib in a.information_bases]
            print(f"Agent: {a.name} | VM: {a.vector_memory_enabled} | Information Bases: {ib_names}")

if __name__ == "__main__":
    asyncio.run(check_agent_info_bases())
