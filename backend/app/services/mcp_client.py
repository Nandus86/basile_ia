"""
MCP Client - Full Model Context Protocol Client Implementation
Supports bidirectional communication: SSE for receiving, POST for sending
"""
import asyncio
import httpx
import json
import uuid
import time
from typing import Dict, Any, Optional, List, Callable, AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class MCPMessageType(str, Enum):
    """MCP Message Types"""
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    ERROR = "error"


@dataclass
class MCPMessage:
    """MCP JSON-RPC Message"""
    jsonrpc: str = "2.0"
    method: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    id: Optional[str] = None


@dataclass
class MCPTool:
    """MCP Tool Definition"""
    name: str
    description: str
    input_schema: Dict[str, Any]


@dataclass
class MCPSession:
    """Active MCP Session"""
    session_id: str
    endpoint: str
    headers: Dict[str, str]
    connected: bool = False
    initialized: bool = False
    tools: List[MCPTool] = field(default_factory=list)
    protocol_version: str = "2024-11-05"
    server_info: Optional[Dict[str, Any]] = None
    capabilities: Dict[str, Any] = field(default_factory=dict)


class MCPClient:
    """
    Full MCP Client implementation supporting:
    - SSE connection for receiving server events
    - JSON-RPC requests via POST
    - Tool discovery and execution
    - Session management
    """
    
    PROTOCOL_VERSION = "2024-11-05"
    
    def __init__(
        self,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 120.0,
        query_params: Optional[Dict[str, str]] = None
    ):
        self.endpoint = endpoint
        self.headers = headers or {}
        self.timeout = timeout
        self.query_params = query_params or {}
        self.session: Optional[MCPSession] = None
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._sse_task: Optional[asyncio.Task] = None
        self._running = False
        self._message_id_counter = 0
        self._events: List[Dict[str, Any]] = []
        self._http_client: Optional[httpx.AsyncClient] = None
        self._mcp_session_id: Optional[str] = None
    
    def _build_url(self, path: str = "") -> str:
        """Build full URL with query params"""
        url = f"{self.endpoint}{path}"
        if self.query_params:
            params = "&".join(f"{k}={v}" for k, v in self.query_params.items())
            url = f"{url}?{params}" if "?" not in url else f"{url}&{params}"
        return url
    
    def _next_id(self) -> str:
        """Generate next request ID"""
        self._message_id_counter += 1
        return str(self._message_id_counter)
    
    async def _send_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None
    ) -> Any:
        """Send JSON-RPC request and wait for response"""
        request_id = self._next_id()
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "id": request_id
        }
        if params:
            message["params"] = params
        
        # Create future for response
        future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future
        
        try:
            if not self._http_client:
                raise Exception("Client not connected")

            # Headers for this request
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
            
            # Inject session ID if we have one (required for Streamable HTTP / n8n)
            if self._mcp_session_id:
                headers["Mcp-Session-Id"] = self._mcp_session_id
            
            # Use the base endpoint for MCP messages
            url = self._build_url()
            
            # Use streaming for SSE responses with persistent client
            async with self._http_client.stream(
                "POST",
                url,
                headers=headers,
                json=message
            ) as response:
                    if response.is_error:
                        error_content = await response.aread()
                        logger.error(f"MCP HTTP Error {response.status_code}: {error_content.decode('utf-8', errors='replace')}")
                        response.raise_for_status()
                    
                    response.raise_for_status()
                    
                    # Capture session ID from response headers (for Streamable HTTP)
                    if "mcp-session-id" in response.headers:
                        self._mcp_session_id = response.headers["mcp-session-id"]
                    
                    content_type = response.headers.get("content-type", "")
                    
                    if "text/event-stream" in content_type:
                        # Parse SSE response
                        current_data = ""
                        async for line in response.aiter_lines():
                            line = line.strip()
                            if line.startswith("data:"):
                                data_part = line[5:].strip()
                                current_data = data_part
                            elif not line and current_data:
                                # End of event
                                try:
                                    parsed = json.loads(current_data)
                                    if "result" in parsed:
                                        return parsed["result"]
                                    elif "error" in parsed:
                                        raise Exception(f"MCP Error: {parsed['error']}")
                                    return parsed
                                except json.JSONDecodeError:
                                    pass
                                current_data = ""
                    else:
                        # Regular JSON response
                        content = await response.aread()
                        result = json.loads(content)
                        if "result" in result:
                            return result["result"]
                        elif "error" in result:
                            raise Exception(f"MCP Error: {result['error']}")
                        return result
                
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            raise Exception(f"Request timeout for method: {method}")
        except Exception as e:
            self._pending_requests.pop(request_id, None)
            raise
        finally:
            self._pending_requests.pop(request_id, None)
    
    async def _handle_sse_event(self, event_type: str, data: Any):
        """Handle incoming SSE event"""
        self._events.append({
            "type": event_type,
            "data": data,
            "timestamp": time.time()
        })
        
        if isinstance(data, dict):
            # Check if it's a response to a pending request
            request_id = data.get("id")
            if request_id and request_id in self._pending_requests:
                future = self._pending_requests.pop(request_id)
                if "error" in data:
                    future.set_exception(Exception(f"MCP Error: {data['error']}"))
                else:
                    future.set_result(data.get("result"))
    
    async def _sse_listener(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Listen to SSE stream and yield events"""
        if not self._http_client:
            return

        headers = {
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache"
        }
        
        url = self._build_url("/sse") if "/sse" not in self.endpoint and not self.endpoint.endswith("/mcp") else self._build_url()
        
        async with self._http_client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()
                
                current_event = {"event": "message", "data": ""}
                
                async for line in response.aiter_lines():
                    line = line.strip()
                    
                    if not line:
                        # Empty line = end of event
                        if current_event["data"]:
                            try:
                                parsed_data = json.loads(current_event["data"])
                                await self._handle_sse_event(current_event["event"], parsed_data)
                                yield {
                                    "type": current_event["event"],
                                    "data": parsed_data
                                }
                            except json.JSONDecodeError:
                                yield {
                                    "type": current_event["event"],
                                    "data": current_event["data"]
                                }
                        current_event = {"event": "message", "data": ""}
                    elif line.startswith("event:"):
                        current_event["event"] = line[6:].strip()
                    elif line.startswith("data:"):
                        data_part = line[5:].strip()
                        if current_event["data"]:
                            current_event["data"] += "\n" + data_part
                        else:
                            current_event["data"] = data_part
    
    async def _send_notification(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None
    ):
        """Send JSON-RPC notification (no response expected)"""
        message = {
            "jsonrpc": "2.0",
            "method": method
        }
        if params:
            message["params"] = params
        
        try:
            if not self._http_client:
                return

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
            
            # Inject session ID if we have one
            if self._mcp_session_id:
                headers["Mcp-Session-Id"] = self._mcp_session_id
            
            url = self._build_url()
            
            await self._http_client.post(
                url,
                headers=headers,
                json=message
            )
                
        except Exception as e:
            logger.error(f"Failed to send notification {method}: {e}")
            # Notifications are best-effort, don't raise

    async def connect(self) -> MCPSession:
        """Establish MCP connection and initialize session"""
        
        # Initialize persistent HTTP client
        self._http_client = httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers=self.headers
        )

        session_id = str(uuid.uuid4())
        
        self.session = MCPSession(
            session_id=session_id,
            endpoint=self.endpoint,
            headers=self.headers
        )
        
        try:
            # Initialize the MCP connection
            init_result = await self._send_request(
                "initialize",
                {
                    "protocolVersion": self.PROTOCOL_VERSION,
                    "capabilities": {
                        "roots": {"listChanged": True},
                        "sampling": {}
                    },
                    "clientInfo": {
                        "name": "Basile_IA_Orch",
                        "version": "1.0.0"
                    }
                }
            )
            
            if init_result:
                self.session.server_info = init_result.get("serverInfo", {})
                self.session.capabilities = init_result.get("capabilities", {})
                self.session.protocol_version = init_result.get("protocolVersion", self.PROTOCOL_VERSION)
                self.session.initialized = True
                
                # Send initialized notification as required by MCP spec
                await self._send_notification("notifications/initialized")
            
            self.session.connected = True
            self._running = True
            
            logger.info(f"MCP Session {session_id} connected to {self.endpoint}")
            
            return self.session
            
        except Exception as e:
            logger.error(f"Failed to connect MCP: {e}")
            raise
    
    async def disconnect(self):
        """Close MCP connection"""
        self._running = False
        
        if self._sse_task:
            self._sse_task.cancel()
            try:
                await self._sse_task
            except asyncio.CancelledError:
                pass
            self._sse_task = None
        
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
            self._mcp_session_id = None
            
        if self.session:
            self.session.connected = False
            logger.info(f"MCP Session {self.session.session_id} disconnected")
            self.session = None
    
    async def list_tools(self) -> List[MCPTool]:
        """Get list of available tools from MCP server"""
        if not self.session or not self.session.connected:
            raise Exception("Not connected to MCP server")
        
        result = await self._send_request("tools/list")
        
        tools = []
        if result and "tools" in result:
            for tool_data in result["tools"]:
                tool = MCPTool(
                    name=tool_data.get("name", ""),
                    description=tool_data.get("description", ""),
                    input_schema=tool_data.get("inputSchema", {})
                )
                tools.append(tool)
        
        self.session.tools = tools
        return tools
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Execute a tool on the MCP server"""
        if not self.session or not self.session.connected:
            raise Exception("Not connected to MCP server")
        
        result = await self._send_request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments or {}
            }
        )
        
        return result
    
    async def get_resources(self) -> List[Dict[str, Any]]:
        """List available resources"""
        if not self.session or not self.session.connected:
            raise Exception("Not connected to MCP server")
        
        result = await self._send_request("resources/list")
        return result.get("resources", []) if result else []
    
    async def read_resource(self, uri: str) -> Any:
        """Read a specific resource"""
        if not self.session or not self.session.connected:
            raise Exception("Not connected to MCP server")
        
        result = await self._send_request(
            "resources/read",
            {"uri": uri}
        )
        return result
    
    def get_events(self) -> List[Dict[str, Any]]:
        """Get all collected SSE events"""
        return self._events.copy()
    
    def clear_events(self):
        """Clear collected events"""
        self._events.clear()


async def execute_mcp_protocol(
    endpoint: str,
    headers: Dict[str, str],
    query_params: Optional[Dict[str, str]] = None,
    action: str = "list_tools",
    tool_name: Optional[str] = None,
    tool_args: Optional[Dict[str, Any]] = None,
    timeout: float = 60.0
) -> Dict[str, Any]:
    """
    High-level function to execute MCP protocol actions
    
    Args:
        endpoint: MCP server endpoint
        headers: Authentication headers
        query_params: Query parameters (like user_id)
        action: Action to perform (initialize, list_tools, call_tool)
        tool_name: Tool name for call_tool action
        tool_args: Tool arguments for call_tool action
        timeout: Request timeout
    
    Returns:
        Dict with result or error
    """
    start_time = time.time()
    client = MCPClient(
        endpoint=endpoint,
        headers=headers,
        query_params=query_params,
        timeout=timeout
    )
    
    try:
        # Connect and initialize
        session = await client.connect()
        
        result = None
        
        if action == "initialize":
            result = {
                "session_id": session.session_id,
                "server_info": session.server_info,
                "capabilities": session.capabilities,
                "protocol_version": session.protocol_version
            }
        
        elif action == "list_tools":
            tools = await client.list_tools()
            result = {
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "input_schema": t.input_schema
                    }
                    for t in tools
                ]
            }
        
        elif action == "call_tool":
            if not tool_name:
                raise ValueError("tool_name is required for call_tool action")
            result = await client.call_tool(tool_name, tool_args)
        
        elif action == "list_resources":
            result = {"resources": await client.get_resources()}
        
        else:
            raise ValueError(f"Unknown action: {action}")
        
        execution_time = (time.time() - start_time) * 1000
        
        return {
            "success": True,
            "result": result,
            "execution_time_ms": execution_time,
            "events": client.get_events()
        }
        
    except Exception as e:
        execution_time = (time.time() - start_time) * 1000
        logger.error(f"MCP execution error: {e}")
        return {
            "success": False,
            "error": str(e),
            "execution_time_ms": execution_time,
            "events": client.get_events() if client else []
        }
    
    finally:
        await client.disconnect()
