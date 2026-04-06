import asyncio
from sqlalchemy import text
from app.database import async_session_maker

async def main():
    with open('/tmp/agent_skills.txt', 'w', encoding='utf-8') as f:
        async with async_session_maker() as db:
            ag_rs = await db.execute(text("SELECT id FROM agents WHERE name = 'BasileIA - Resposta Final'"))
            ag_id = ag_rs.scalar_one_or_none()
            if not ag_id:
                f.write('Agent "BasileIA - Resposta Final" not found\n')
                return
            
            f.write(f'Agent ID: {ag_id}\n\n')
            
            rs = await db.execute(text("SELECT s.name, s.content_md FROM agent_skill_access asa JOIN skills s ON asa.skill_id = s.id WHERE asa.agent_id = :ag_id"), {'ag_id': ag_id})
            rows = rs.all()
            if not rows:
                f.write('No skills found assigned directly to this agent.\n')
            else:
                for r in rows:
                    f.write(f'--- SKILL: {r.name} ---\n{r.content_md}\n\n')

asyncio.run(main())
