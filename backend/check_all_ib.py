import asyncio
from sqlalchemy import text
from app.database import engine

async def check_all():
    async with engine.connect() as conn:
        ib_res = await conn.execute(text("SELECT id, name, code, is_active FROM information_bases"))
        ibs = ib_res.all()
        print(f"Total Information Bases: {len(ibs)}")
        for i in ibs:
            print(f"- {i.name} ({i.code}) | Active: {i.is_active}")
            
        ass_res = await conn.execute(text("SELECT agent_id, information_base_id FROM agent_info_base_access"))
        ass = ass_res.all()
        print(f"Total Agent-IB associations: {len(ass)}")
        for a in ass:
            print(f"- Agent {a.agent_id} -> IB {a.information_base_id}")

if __name__ == "__main__":
    asyncio.run(check_all())
