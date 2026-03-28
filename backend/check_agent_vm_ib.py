import asyncio
from sqlalchemy import text
from app.database import engine

async def check_agent_settings():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT id, name, vector_memory_enabled, is_orchestrator FROM agents"))
        agents = result.all()
        for a in agents:
            agent_id, name, vm_enabled, is_orch = a
            # Check Information Bases
            ib_res = await conn.execute(text(
                "SELECT ib.name FROM information_bases ib "
                "JOIN agent_info_base_access aiba ON ib.id = aiba.information_base_id "
                "WHERE aiba.agent_id = :id"
            ), {"id": agent_id})
            ib_names = [r[0] for r in ib_res.all()]
            print(f"Agent: {name} (ID: {agent_id})")
            print(f"  - VM Enabled: {vm_enabled}")
            print(f"  - Is Orchestrator: {is_orch}")
            print(f"  - Information Bases: {ib_names}")

if __name__ == "__main__":
    asyncio.run(check_agent_settings())
