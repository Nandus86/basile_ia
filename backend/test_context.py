
import asyncio
from app.context import set_request_context, get_request_context
from app.services.mcp_tools import MCPToolExecutor

async def mock_tool_execution():
    # Simulate setting context in request
    test_context = {"body-apikey": "12345", "other": "value"}
    set_request_context(test_context)
    print(f"Set context: {test_context}")
    
    # Define a mock executor that behaves like the one in mcp_tools
    async def execute_tool(**kwargs):
        from app.context import get_request_context
        ctx = get_request_context()
        print(f"Context inside tool: {ctx}")
        final_args = {**ctx, **kwargs}
        print(f"Final args: {final_args}")
        return final_args

    # Run tool
    print("Executing tool with empty kwargs...")
    result = await execute_tool()
    
    assert result["body-apikey"] == "12345"
    print("Context propagation successful!")

if __name__ == "__main__":
    asyncio.run(mock_tool_execution())
