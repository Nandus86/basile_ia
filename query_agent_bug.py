import asyncio
from sqlalchemy import text
from app.database import async_session_maker

async def main():
    with open('/tmp/agent_ec696832.txt', 'w', encoding='utf-8') as f:
        async with async_session_maker() as db:
            ag_id = 'ec696832-82c4-4b33-b100-9cd2a0ed94b7'
            
            # 1. Get Agent details
            agent_rs = await db.execute(text("SELECT name, system_prompt FROM agents WHERE id = :ag_id"), {'ag_id': ag_id})
            agent = agent_rs.first()
            if not agent:
                f.write('Agent not found\n')
                return
            f.write(f'=== AGENT: {agent.name} ===\n\n{agent.system_prompt}\n\n')
            
            # 2. Get Skills
            f.write('=== SKILLS ===\n\n')
            skills_rs = await db.execute(text("SELECT s.name, s.content_md FROM agent_skill_access asa JOIN skills s ON asa.skill_id = s.id WHERE asa.agent_id = :ag_id"), {'ag_id': ag_id})
            for s in skills_rs:
                f.write(f'--- SKILL: {s.name} ---\n{s.content_md}\n\n')
                
            # 3. Get Collaborators
            f.write('=== COLLABORATORS ===\n\n')
            collab_rs = await db.execute(text("SELECT a.name, a.system_prompt FROM agent_collaborators c JOIN agents a ON c.collaborator_id = a.id WHERE c.agent_id = :ag_id"), {'ag_id': ag_id})
            for c in collab_rs:
                f.write(f'--- COLLAB: {c.name} ---\n{c.system_prompt}\n\n')

asyncio.run(main())
