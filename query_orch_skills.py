import asyncio
from sqlalchemy import text
from app.database import async_session_maker

async def main():
    with open('/tmp/agent_skills_orch.txt', 'w', encoding='utf-8') as f:
        async with async_session_maker() as db:
            ag_id = '3e290904-8860-43f9-81eb-544620071562'
            f.write(f'Agent ID: {ag_id}\n\n')
            rs = await db.execute(text("SELECT s.name, s.content_md FROM agent_skill_access asa JOIN skills s ON asa.skill_id = s.id WHERE asa.agent_id = :ag_id"), {'ag_id': ag_id})
            rows = rs.all()
            if not rows:
                f.write('No skills found assigned directly to this agent.\n')
            else:
                for r in rows:
                    f.write(f'--- SKILL: {r.name} ---\n{r.content_md}\n\n')

asyncio.run(main())
