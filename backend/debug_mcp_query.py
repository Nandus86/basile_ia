import asyncio
import json
from sqlalchemy import text
from app.database import async_session_maker

async def run():
    async with async_session_maker() as session:
        # Get the MCP 'HTTP Eventos - list_all_events'
        result = await session.execute(
            text("SELECT id, name, endpoint, method, query_template, body_template, headers FROM mcps WHERE name LIKE '%Eventos%list_all%'")
        )
        rows = result.fetchall()
        for row in rows:
            print(f"ID: {row[0]}")
            print(f"Name: {row[1]}")
            print(f"Endpoint: {row[2]}")
            print(f"Method: {row[3]}")
            print(f"Query Template: {json.dumps(row[4], indent=2, ensure_ascii=False) if row[4] else 'NULL'}")
            print(f"Body Template: {json.dumps(row[5], indent=2, ensure_ascii=False) if row[5] else 'NULL'}")
            print(f"Headers: {json.dumps(row[6], indent=2, ensure_ascii=False) if row[6] else 'NULL'}")
            print("---")

asyncio.run(run())
