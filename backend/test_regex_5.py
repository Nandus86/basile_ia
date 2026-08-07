import asyncio
import json
import urllib.parse
from app.services.mcp_tools import MCPToolExecutor, _inject_request_params
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
    
    # Mocking the MCP object
    mcp = MCP(
        name="Eventos - list all events",
        endpoint="https://dash.basileia.global/api/events/n8n/{{ $request.system.phone }}?church_id={{ $request.church._id }}",
        method="GET",
        protocol="http",
        query_template={"church_id": "{{ $request.church._id }}"}
    )
    
    merged_ctx = payload  # mock raw_ctx merge
    
    endpoint_str = urllib.parse.unquote(mcp.endpoint or '')
    body_str = json.dumps(mcp.body_template or {})
    headers_str = json.dumps(mcp.headers or {})
    query_template = getattr(mcp, 'query_template', {}) or {}
    query_str = json.dumps(query_template)
    
    pre_resolved_templates = {
        'endpoint_str': _inject_request_params(endpoint_str, merged_ctx),
        'body_str': _inject_request_params(body_str, merged_ctx),
        'headers_str': _inject_request_params(headers_str, merged_ctx),
        'query_str': _inject_request_params(query_str, merged_ctx),
    }
    
    print("Pre-resolved Query String:", pre_resolved_templates['query_str'])
    print("Pre-resolved Endpoint String:", pre_resolved_templates['endpoint_str'])

if __name__ == "__main__":
    asyncio.run(test())
