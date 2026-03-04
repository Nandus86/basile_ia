"""
MCP Tools Service - Converts MCP tools to LangChain tools for agents
"""
import asyncio
import json
from typing import List, Dict, Any, Optional, Callable
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import logging

from app.models.mcp import MCP
from app.models.agent import Agent
from app.services.mcp_client import MCPClient, execute_mcp_protocol

logger = logging.getLogger(__name__)


def _is_mcp_error_response(text: str) -> bool:
    """Check if an MCP response indicates a schema validation error.
    Only detects actual validation failures, NOT generic error fields in responses."""
    # Only check for actual schema validation errors that indicate wrong parameters
    validation_errors = [
        "did not match expected schema",
        "expected string, received null",
        "required field",
    ]
    text_lower = text.lower()
    return any(err in text_lower for err in validation_errors)


def _build_error_diagnostics(
    tool_name: str,
    error_msg: str,
    sent_args: Dict[str, Any],
    null_keys: list,
    flat_context: Dict[str, Any]
) -> str:
    """Build a rich error response that helps the LLM retry intelligently"""
    # Show what was sent vs what was null
    sent_summary = {}
    for k, v in sent_args.items():
        if v is not None:
            if isinstance(v, str) and len(v) > 50:
                sent_summary[k] = v[:50] + "..."
            elif isinstance(v, dict):
                sent_summary[k] = "{...}"
            else:
                sent_summary[k] = v
        else:
            sent_summary[k] = "NULL ← precisa preencher"
    
    # Find available values from context that could fill nulls
    suggestions = {}
    for null_key in null_keys:
        # Look for similar keys in flat_context
        candidates = []
        for ctx_key, ctx_val in flat_context.items():
            if null_key in ctx_key or ctx_key in null_key:
                if not isinstance(ctx_val, (dict, list)):
                    candidates.append(f"{ctx_key}={ctx_val}")
        if candidates:
            suggestions[null_key] = candidates[:3]
    
    diagnostics = {
        "tool_error": True,
        "tool_name": tool_name,
        "error_message": error_msg[:500],
        "args_sent": sent_summary,
        "null_args": null_keys,
        "suggestions": suggestions,
        "instruction": (
            "A ferramenta retornou um erro. Analise o erro acima e tente chamar "
            "a ferramenta novamente com os parâmetros corretos. "
            "Os campos marcados como NULL precisam ser preenchidos com valores válidos. "
            "Use as sugestões acima se disponíveis."
        )
    }
    return json.dumps(diagnostics, indent=2, ensure_ascii=False)


class MCPToolExecutor:
    """
    Converts MCP tools to LangChain tools that agents can use.
    """
    
    def __init__(self, db: AsyncSession, context_data: Optional[Dict[str, Any]] = None):
        self.db = db
        self.context_data = context_data or {}
        self._tool_cache: Dict[str, List[StructuredTool]] = {}
    
    async def get_mcp_by_id(self, mcp_id: str) -> Optional[MCP]:
        """Fetch MCP by ID"""
        from uuid import UUID
        result = await self.db.execute(
            select(MCP).where(MCP.id == UUID(mcp_id))
        )
        return result.scalar_one_or_none()
    
    async def get_agent_mcps(self, agent_id: str) -> List[MCP]:
        """Get all MCPs associated with an agent"""
        from uuid import UUID
        result = await self.db.execute(
            select(Agent)
            .options(selectinload(Agent.mcps))
            .where(Agent.id == UUID(agent_id))
        )
        agent = result.scalar_one_or_none()
        if agent and agent.mcps:
            return [mcp for mcp in agent.mcps if mcp.is_active]
        return []
    
    async def discover_mcp_tools(self, mcp: MCP) -> List[Dict[str, Any]]:
        """Discover available tools from an MCP server"""
        if mcp.protocol != "mcp":
            # For non-MCP protocols, return a single "execute" tool
            return [{
                "name": f"execute_{mcp.name.lower().replace(' ', '_')}",
                "description": mcp.description or f"Execute {mcp.name}",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "params": {
                            "type": "object",
                            "description": "Parameters to send to the endpoint"
                        }
                    },
                    "required": []
                },
                "mcp_id": str(mcp.id),
                "protocol": mcp.protocol
            }]
        
        # For MCP protocol, discover tools from the server
        query_params = {}
        body = {**mcp.body_template} if mcp.body_template else {}
        for key in ["user_id", "session_id"]:
            if key in body:
                query_params[key] = str(body.pop(key))
        
        result = await execute_mcp_protocol(
            endpoint=mcp.endpoint,
            headers=mcp.headers or {},
            query_params=query_params,
            action="list_tools",
            timeout=float(mcp.timeout_seconds or 60)
        )
        
        if result.get("success") and result.get("result", {}).get("tools"):
            tools = []
            for tool in result["result"]["tools"]:
                tools.append({
                    "name": tool.get("name", "unknown"),
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("input_schema", {"type": "object", "properties": {}}),
                    "mcp_id": str(mcp.id),
                    "protocol": "mcp"
                })
            return tools
        
        return []
    
    def _create_tool_executor(self, mcp_id: str, tool_name: str, protocol: str, all_params: list) -> Callable:
        """Create an async executor function for a tool.
        all_params: ALL parameter names the MCP tool expects (including context ones)
        """
        async def execute_tool(**kwargs) -> str:
            from app.context import get_request_context
            import os
            
            context = self.context_data.copy()
            req_ctx = get_request_context()
            if req_ctx:
                context.update(req_ctx)
            
            # Recursively flatten nested context
            flat_context = {}
            def flatten_dict(d, prefix_parts=None):
                if prefix_parts is None:
                    prefix_parts = []
                for key, value in d.items():
                    current_parts = prefix_parts + [str(key)]
                    for i in range(len(current_parts)):
                        flat_key = "-".join(current_parts[i:])
                        if flat_key not in flat_context:
                            flat_context[flat_key] = value
                    if isinstance(value, dict):
                        flatten_dict(value, current_parts)
            
            if context:
                flatten_dict(context)
            
            # Build final_args using ALL expected params, not just kwargs
            final_args = {}
            for param in all_params:
                # Priority: kwargs (LLM) > flat_context > env vars
                if param in kwargs and kwargs[param] is not None:
                    final_args[param] = kwargs[param]
                elif param in flat_context and flat_context[param] is not None:
                    val = flat_context[param]
                    final_args[param] = str(val) if not isinstance(val, (dict, list)) else val
                else:
                    env_key = param.upper().replace('-', '_')
                    env_val = os.environ.get(env_key) or os.environ.get(param)
                    if env_val:
                        final_args[param] = env_val
            
            # Include any extra LLM kwargs not in all_params
            for k, v in kwargs.items():
                if k not in final_args and v is not None:
                    final_args[k] = v
            
            filled = sum(1 for p in all_params if p in final_args and final_args[p] is not None)
            print(f"[MCPTool] 🛠️ {tool_name} — {filled}/{len(all_params)} params filled")
            missing = [p for p in all_params if p not in final_args]
            if missing:
                print(f"[MCPTool] ⚠️ Missing: {missing}")
            
            try:
                mcp = await self.get_mcp_by_id(mcp_id)
                if not mcp:
                    return json.dumps({"error": f"MCP {mcp_id} not found"})
                
                if protocol == "mcp":
                    query_params = {}
                    body = {**mcp.body_template} if mcp.body_template else {}
                    for key in ["user_id", "session_id"]:
                        if key in body:
                            query_params[key] = str(body.pop(key))
                    
                    result = await execute_mcp_protocol(
                        endpoint=mcp.endpoint,
                        headers=mcp.headers or {},
                        query_params=query_params,
                        action="call_tool",
                        tool_name=tool_name,
                        tool_args=final_args,
                        timeout=float(mcp.timeout_seconds or 60)
                    )
                    
                    if result.get("success"):
                        return json.dumps(result.get("result", {}), indent=2, ensure_ascii=False)
                    else:
                        return json.dumps({"error": result.get("error", "Unknown error")})
                
                else:
                    import httpx
                    timeout = float(mcp.timeout_seconds or 30)
                    body = {**mcp.body_template} if mcp.body_template else {}
                    body.update(final_args)
                    
                    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                        if mcp.method.upper() == "GET":
                            response = await client.get(mcp.endpoint, headers=mcp.headers, params=body)
                        else:
                            response = await client.post(mcp.endpoint, headers=mcp.headers, json=body)
                        
                        response.raise_for_status()
                        return json.dumps(response.json(), indent=2, ensure_ascii=False)
                        
            except Exception as e:
                logger.error(f"Tool execution error: {e}")
                return json.dumps({"error": str(e)})
        
        return execute_tool
    
    def _schema_to_pydantic(self, schema: Dict[str, Any], tool_name: str) -> type:
        """Convert JSON schema to Pydantic model.
        Context fields (body-*, member-*, church-*) are EXCLUDED so the LLM
        only sees fields it needs to actively fill.
        """
        properties = schema.get("properties", {})
        context_prefixes = ("body-", "member-", "church-")
        
        fields = {}
        for prop_name, prop_schema in properties.items():
            if not isinstance(prop_schema, dict):
                continue
            
            # Skip context fields — auto-injected at execution time
            if any(prop_name.startswith(p) for p in context_prefixes):
                continue
                
            prop_type = prop_schema.get("type", "string")
            description = str(prop_schema.get("description", ""))[:500]
            
            type_mapping = {
                "string": str,
                "integer": int,
                "number": float,
                "boolean": bool,
                "array": list,
                "object": dict
            }
            python_type = type_mapping.get(prop_type, str)
            
            safe_name = prop_name.replace("-", "_")
            if safe_name != prop_name:
                fields[safe_name] = (
                    Optional[python_type],
                    Field(default=None, description=description, alias=prop_name)
                )
            else:
                fields[safe_name] = (
                    Optional[python_type],
                    Field(default=None, description=description)
                )
        
        # No fallback needed — empty model means tool takes no LLM input
        # (all fields are auto-injected from context)
        
        model_name = f"{tool_name.replace('/', '_').replace('-', '_')}Input"
        model = create_model(model_name, **fields)
        model.model_config["populate_by_name"] = True
        return model
    
    async def create_langchain_tools(self, mcp: MCP) -> List[StructuredTool]:
        """Create LangChain tools from an MCP"""
        cache_key = str(mcp.id)
        
        # Check cache
        if cache_key in self._tool_cache:
            return self._tool_cache[cache_key]
        
        tools = []
        
        try:
            # Discover available tools
            discovered_tools = await self.discover_mcp_tools(mcp)
            
            for tool_def in discovered_tools:
                tool_name = tool_def["name"]
                description = tool_def.get("description", f"Execute {tool_name}")
                input_schema = tool_def.get("input_schema", {})
                
                # ALL params the MCP expects (including context ones)
                all_params = list(input_schema.get("properties", {}).keys())
                
                # Pydantic model for LLM (context fields excluded)
                args_schema = self._schema_to_pydantic(input_schema, tool_name)
                
                # Executor knows ALL params so it can fill context
                executor = self._create_tool_executor(
                    mcp_id=str(mcp.id),
                    tool_name=tool_name,
                    protocol=tool_def.get("protocol", "http"),
                    all_params=all_params
                )
                
                # Create LangChain tool
                tool = StructuredTool.from_function(
                    coroutine=executor,
                    name=tool_name,
                    description=description[:200] if len(description) > 200 else description,
                    args_schema=args_schema,
                    return_direct=False
                )
                tools.append(tool)
                
        except Exception as e:
            logger.error(f"Error creating tools for MCP {mcp.name}: {e}")
        
        # Cache tools
        self._tool_cache[cache_key] = tools
        
        return tools
    
    async def get_agent_tools(self, agent_id: str) -> List[StructuredTool]:
        """Get all LangChain tools available to an agent"""
        all_tools = []
        
        mcps = await self.get_agent_mcps(agent_id)
        
        for mcp in mcps:
            mcp_tools = await self.create_langchain_tools(mcp)
            all_tools.extend(mcp_tools)
            logger.info(f"Added {len(mcp_tools)} tools from MCP '{mcp.name}' for agent {agent_id}")
        
        return all_tools
    
    def clear_cache(self, mcp_id: Optional[str] = None):
        """Clear tool cache"""
        if mcp_id:
            self._tool_cache.pop(mcp_id, None)
        else:
            self._tool_cache.clear()


async def get_tools_for_agent(db: AsyncSession, agent_id: str, context_data: Optional[Dict[str, Any]] = None) -> List[StructuredTool]:
    """
    Convenience function to get all tools for an agent.
    
    Args:
        db: Database session
        agent_id: Agent UUID string
        context_data: Optional context data for tool injection
    
    Returns:
        List of LangChain StructuredTool objects
    """
    executor = MCPToolExecutor(db, context_data)
    return await executor.get_agent_tools(agent_id)
