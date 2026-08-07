import asyncio
from app.database import async_session_maker
from app.services.mcp_tools import MCPToolExecutor
from sqlalchemy import select
from app.models.mcp import MCP

async def test():
    payload = {
      "message": "quais eventos tem na igreja?",
      "session_id": "test_123",
      "church": {
        "_id": "68ff5a3c4177621d0b00faa9",
      },
      "system": {
        "phone": "5543999284670"
      }
    }
    
    async with async_session_maker() as db:
        mcp = await db.scalar(select(MCP).where(MCP.name == "Eventos - list all events"))
        if not mcp:
            print("MCP not found")
            return
            
        print("Endpoint DB:", mcp.endpoint)
        print("Query DB:", mcp.query_template)
        
        executor = MCPToolExecutor(db, payload)
        tools = await executor.create_langchain_tools([mcp])
        
        print("\n--- After create_langchain_tools ---")
        for tool in tools:
            print("Tool created:", tool.name)
            
        print("\n--- Calling tool ---")
        try:
            # Pydantic may complain if we don't pass the exact kwargs, but we pass empty
            res = await tools[0].ainvoke({})
            print(res)
        except Exception as e:
            print("Exception during tool execution:", e)

if __name__ == "__main__":
    asyncio.run(test())
