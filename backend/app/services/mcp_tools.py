"""
MCP Tools Service - Converts MCP tools to LangChain tools for agents
"""
import asyncio
import json
import re
import ast
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


def _extract_from_ai_params(text: str) -> dict:
    params = {}
    if not text:
        return params
    matches = re.finditer(r'\{\{\s*\$fromAI\((.*?)\)\s*\}\}', text)
    for m in matches:
        args_str = m.group(1)
        try:
            # Safely evaluate arguments without regex guessing
            args = ast.literal_eval(f'({args_str},)')
            if not args:
                continue
            name = args[0]
            desc = args[1] if len(args) > 1 else f"Parameter {name}"
            type_str = args[2] if len(args) > 2 else "string"
            default = args[3] if len(args) > 3 else None
            
            params[name] = {
                "description": desc,
                "type": type_str,
                "default": default
            }
        except:
            pass
    return params


def _get_value_by_path(data: dict, path: str) -> Any:
    """Extrai valor de um dicionário usando notação de ponto (a.b.c)"""
    if not data or not path:
        return None
    
    parts = path.split('.')
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            idx = int(part)
            current = current[idx] if idx < len(current) else None
        else:
            return None
    return current


def _inject_request_params(text: str, context_data: dict) -> str:
    """Substitui {{ $request.path.to.field }} por valores reais do context_data"""
    if not text or not context_data:
        return text
    
    def replacer(match):
        path = match.group(1).strip()
        val = _get_value_by_path(context_data, path)
        
        if val is None:
            return match.group(0)  # Mantém o placeholder se não encontrar
            
        if isinstance(val, bool):
            return "true" if val else "false"
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False)
        return str(val)
            
    return re.sub(r'\{\{\s*\$request\.(.*?)\s*\}\}', replacer, text)

def _inject_from_ai_params(text: str, kwargs: dict) -> tuple[str, set]:
    """Replace {{ $fromAI(...) }} with real values from kwargs"""
    if not text:
        return text, set()
    
    used_args = set()
    def replacer(match):
        args_str = match.group(1)
        try:
            args = ast.literal_eval(f'({args_str},)')
            if not args:
                return match.group(0)
            name = args[0]
            default = args[3] if len(args) > 3 else None
            
            val = kwargs.get(name)
            if val is not None:
                used_args.add(name)
                if isinstance(val, bool):
                     return "true" if val else "false"
                return str(val)
            elif default is not None:
                used_args.add(name)
                if isinstance(default, bool):
                     return "true" if default else "false"
                return str(default)
            return match.group(0)
        except:
            return match.group(0)
            
    result = re.sub(r'\{\{\s*\$fromAI\((.*?)\)\s*\}\}', replacer, text)
    return result, used_args


def _apply_response_mapping(data: dict, mapping: dict) -> dict:
    """Extrai partes de um JSON de resposta profundo e mapeia como especificado pelo admin"""
    if not mapping or not isinstance(mapping, dict):
        return data

    def _extract(obj, path):
        if not path:
            return obj
            
        # Normaliza o path: transforma body[*]._id em body.[*]._id
        # e body[0]._id em body.0._id para facilitar o split
        p = str(path).replace('[*]', '.[*].')
        p = re.sub(r'\[(\d+)\]', r'.\1.', p)
        # Limpa pontos duplos e partes vazias
        parts = [part for part in p.replace('..', '.').strip('.').split('.') if part]
        
        current = obj
        for i, part in enumerate(parts):
            if part == '[*]':
                if isinstance(current, list):
                    remaining_path = '.'.join(parts[i+1:])
                    return [_extract(item, remaining_path) for item in current]
                return None
            elif isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit():
                idx = int(part)
                current = current[idx] if idx < len(current) else None
            else:
                return None
        return current

    result = {}
    for key, path in mapping.items():
        if isinstance(path, str):
            result[key] = _extract(data, path)
        else:
            result[key] = path  # fallback

    # Filtra apenas os valores que não são None (que foram encontrados)
    filtered_result = {k: v for k, v in result.items() if v is not None}
            
    # Se o mapeamento não resultou em nada útil, devolve o dado original
    # para que o Agente ou UI tenham acesso ao payload completo.
    return filtered_result if filtered_result else data


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
        """Get all MCPs associated with an agent (direct + via groups)"""
        from uuid import UUID
        from app.models.mcp_group import MCPGroup
        result = await self.db.execute(
            select(Agent)
            .options(
                selectinload(Agent.mcps),
                selectinload(Agent.mcp_groups).selectinload(MCPGroup.mcps)
            )
            .where(Agent.id == UUID(agent_id))
        )
        agent = result.scalar_one_or_none()
        
        all_mcps = []
        seen_ids = set()
        
        if agent:
            if agent.mcps:
                for mcp in agent.mcps:
                    if mcp.is_active and mcp.id not in seen_ids:
                        # Store group context magically if needed, but for normal fetch just return the mcp
                        all_mcps.append(mcp)
                        seen_ids.add(mcp.id)
                        
            if getattr(agent, "mcp_groups", None):
                for group in agent.mcp_groups:
                    if group.is_active and group.mcps:
                        for mcp in group.mcps:
                            if mcp.is_active and mcp.id not in seen_ids:
                                # Inject group description as an attribute for later use in create_langchain_tools
                                mcp._group_description_context = group.description
                                all_mcps.append(mcp)
                                seen_ids.add(mcp.id)
                                
        return all_mcps
    
    async def discover_mcp_tools(self, mcp: MCP) -> List[Dict[str, Any]]:
        """Discover available tools from an MCP server"""
        if mcp.protocol != "mcp":
            # Extract $fromAI parameters
            ai_params = {}
            if mcp.endpoint:
                import urllib.parse
                decoded_endpoint = urllib.parse.unquote(mcp.endpoint)
                ai_params.update(_extract_from_ai_params(decoded_endpoint))
            if mcp.headers:
                ai_params.update(_extract_from_ai_params(json.dumps(mcp.headers)))
            if mcp.body_template:
                ai_params.update(_extract_from_ai_params(json.dumps(mcp.body_template)))
            query_template = getattr(mcp, "query_template", {}) or {}
            if query_template:
                ai_params.update(_extract_from_ai_params(json.dumps(query_template)))
            
            schema_properties = {
                "params": {
                    "type": "object",
                    "description": "Parameters to send to the endpoint"
                }
            }
            required_fields = []
            
            for p_name, p_info in ai_params.items():
                schema_properties[p_name] = {
                    "type": p_info["type"],
                    "description": p_info["description"]
                }
                if p_info["default"] is None:
                    required_fields.append(p_name)
            
            if not ai_params:
                required_fields = []

            import re
            safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', mcp.name)
            
            # For non-MCP protocols, return a single "execute" tool
            return [{
                "name": f"execute_{safe_name}",
                "description": mcp.description or f"Execute {mcp.name}",
                "input_schema": {
                    "type": "object",
                    "properties": schema_properties,
                    "required": required_fields
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
            import re
            tools = []
            for tool in result["result"]["tools"]:
                raw_name = tool.get("name", "unknown")
                safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', raw_name)
                tools.append({
                    "name": safe_name,
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("input_schema", {"type": "object", "properties": {}}),
                    "mcp_id": str(mcp.id),
                    "protocol": "mcp"
                })
            return tools
        
        return []
    
    def _create_tool_executor(self, mcp_id: str, tool_name: str, protocol: str, all_params: list,
                              pre_resolved_templates: Optional[Dict[str, Any]] = None) -> Callable:
        """Create an async executor function for a tool.
        all_params: ALL parameter names the MCP tool expects (including context ones)
        pre_resolved_templates: Templates with {{ $request }} already resolved
        """
        _pre_resolved = pre_resolved_templates or {}
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
                    # Smart fallback for context
                    found_fallback = False
                    for ctx_key, ctx_val in flat_context.items():
                        if param in ctx_key or ctx_key in param:
                            final_args[param] = str(ctx_val) if not isinstance(ctx_val, (dict, list)) else ctx_val
                            found_fallback = True
                            break
                        # Also check if just the suffix matches (e.g. member-phone matches global-phone)
                        if '-' in param and '-' in ctx_key:
                            if param.split('-', 1)[-1] == ctx_key.split('-', 1)[-1]:
                                final_args[param] = str(ctx_val) if not isinstance(ctx_val, (dict, list)) else ctx_val
                                found_fallback = True
                                break
                    
                    if not found_fallback:
                        env_key = param.upper().replace('-', '_')
                        env_val = os.environ.get(env_key) or os.environ.get(param)
                        if env_val:
                            final_args[param] = env_val
            
            # Include any extra LLM kwargs not in all_params
            for k, v in kwargs.items():
                if k not in final_args and v is not None:
                    final_args[k] = v
            
            filled = sum(1 for p in all_params if p in final_args and final_args[p] is not None)
            missing = [p for p in all_params if p not in final_args]
            logger.info(
                f"[MCPTool] 🛠️  INVOKE  tool={tool_name!r}  protocol={protocol!r}  "
                f"params={filled}/{len(all_params)} preenchidos  missing={missing or 'none'}"
            )
            logger.debug(f"[MCPTool] 📦 args enviados: {json.dumps(final_args, default=str, ensure_ascii=False)[:800]}")
            
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
                    
                    # For pure 'mcp' protocol, we shouldn't send injected vars like 
                    # 'bodyapikey' as tool arguments, since the remote MCP server won't expect them.
                    cleaned_args = final_args.copy()
                    
                    # Discover all keys that were used as injected placeholders
                    used_all = set()
                    _, u_body = _inject_from_ai_params(json.dumps(mcp.body_template or {}), final_args)
                    _, u_headers = _inject_from_ai_params(json.dumps(mcp.headers or {}), final_args)
                    _, u_query = _inject_from_ai_params(json.dumps(getattr(mcp, "query_template", {}) or {}), final_args)
                    import urllib.parse
                    _, u_endpoint = _inject_from_ai_params(urllib.parse.unquote(mcp.endpoint or ""), final_args)
                    
                    used_all.update(u_body, u_headers, u_query, u_endpoint)
                    
                    # Remove the mapping keys from arguments being forwarded to the remote tool
                    for key in used_all:
                        cleaned_args.pop(key, None)
                    
                    import time as _time
                    _t0 = _time.monotonic()
                    logger.info(
                        f"[MCPTool] 🌐 MCP CALL  tool={tool_name!r}  "
                        f"endpoint={mcp.endpoint!r}  args_keys={list(cleaned_args.keys())}"
                    )
                    # Log do payload de entrada (parâmetros enviados ao MCP)
                    logger.info(f"[MCPTool] 📤 PAYLOAD ENTRADA (MCP) tool={tool_name!r}: {json.dumps(cleaned_args, ensure_ascii=False)}")
                    
                    result = await execute_mcp_protocol(
                        endpoint=mcp.endpoint,
                        headers=mcp.headers or {},
                        query_params=query_params,
                        action="call_tool",
                        tool_name=tool_name,
                        tool_args=cleaned_args,
                        timeout=float(mcp.timeout_seconds or 60)
                    )
                    _elapsed = (_time.monotonic() - _t0) * 1000

                    if result.get("success"):
                        res_data = result.get("result", {})
                        # Log do payload de saída (bruto para MCP protocol)
                        logger.info(f"[MCPTool] 📦 PAYLOAD SAÍDA (MCP): {json.dumps(res_data, ensure_ascii=False)[:1000]}")
                        
                        raw = json.dumps(res_data, indent=2, ensure_ascii=False)
                        logger.info(
                            f"[MCPTool] ✅ MCP OK  tool={tool_name!r}  "
                            f"elapsed={_elapsed:.0f}ms  response_preview={raw[:500]!r}"
                        )
                        return raw
                    else:
                        err = result.get("error", "Unknown error")
                        logger.warning(
                            f"[MCPTool] ❌ MCP ERRO  tool={tool_name!r}  "
                            f"elapsed={_elapsed:.0f}ms  error={err!r}"
                        )
                        return json.dumps({"error": err})
                
                else:
                    import httpx
                    timeout = float(mcp.timeout_seconds or 30)
                    
                    import urllib.parse
                    
                    # Use pre-resolved templates if available ({{ $request }} already filled)
                    body_str = _pre_resolved.get('body_str') or json.dumps(mcp.body_template or {})
                    headers_str = _pre_resolved.get('headers_str') or json.dumps(mcp.headers or {})
                    query_str = _pre_resolved.get('query_str') or json.dumps(getattr(mcp, 'query_template', {}) or {})
                    endpoint_str = _pre_resolved.get('endpoint_str') or urllib.parse.unquote(mcp.endpoint or '')
                    
                    used_all = set()
                    body_str, u_body = _inject_from_ai_params(body_str, final_args)
                    headers_str, u_headers = _inject_from_ai_params(headers_str, final_args)
                    query_str, u_query = _inject_from_ai_params(query_str, final_args)
                    endpoint_str, u_endpoint = _inject_from_ai_params(endpoint_str, final_args)
                    
                    # Safety net: inject any remaining $request params not pre-resolved
                    body_str = _inject_request_params(body_str, context)
                    headers_str = _inject_request_params(headers_str, context)
                    query_str = _inject_request_params(query_str, context)
                    endpoint_str = _inject_request_params(endpoint_str, context)
                    
                    used_all.update(u_body, u_headers, u_query, u_endpoint)
                    
                    body = json.loads(body_str)
                    headers = json.loads(headers_str)
                    query = json.loads(query_str)
                    
                    # Also include explicit 'params' object passed by the LLM (legacy behavior)
                    if "params" in final_args and isinstance(final_args["params"], dict):
                        if mcp.method.upper() == "GET":
                            query.update(final_args["params"])
                        else:
                            body.update(final_args["params"])
                    else:
                        # Forward remaining non-macro args into body/query, skipping ones already used in macros
                        for k, v in final_args.items():
                            if k not in ["params"] and k not in used_all:
                                if mcp.method.upper() == "GET":
                                    query[k] = v
                                else:
                                    body[k] = v
                    
                    # Prevent httpx 'ascii' codec error handling non-ASCII headers
                    safe_headers = {}
                    for hk, hv in headers.items():
                        safe_headers[str(hk).encode("utf-8")] = str(hv).encode("utf-8")
                    
                    # Log do payload de entrada (corpo/query da requisição HTTP)
                    logger.info(f"[MCPTool] 📤 PAYLOAD ENTRADA (HTTP) tool={tool_name!r}: body={json.dumps(body, ensure_ascii=False)} query={json.dumps(query, ensure_ascii=False)}")
                    
                    import time as _time
                    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                        method = mcp.method.upper()
                        _body_log = json.dumps(body, default=str, ensure_ascii=False)[:500] if body else "{}"
                        _query_log = json.dumps(query, default=str, ensure_ascii=False)[:300] if query else "{}"
                        logger.info(
                            f"[MCPTool] 🌐 HTTP CALL  tool={tool_name!r}  method={method}  "
                            f"url={endpoint_str!r}  body={_body_log}  query={_query_log}"
                        )
                        _t0 = _time.monotonic()
                        if method == "GET":
                            response = await client.get(endpoint_str, headers=safe_headers, params=query)
                        elif method == "POST":
                            response = await client.post(endpoint_str, headers=safe_headers, params=query, json=body)
                        elif method == "PUT":
                            response = await client.put(endpoint_str, headers=safe_headers, params=query, json=body)
                        elif method == "PATCH":
                            response = await client.patch(endpoint_str, headers=safe_headers, params=query, json=body)
                        elif method == "DELETE":
                            response = await client.delete(endpoint_str, headers=safe_headers, params=query)
                        else:
                            raise ValueError(f"Unsupported HTTP method: {mcp.method}")
                        _elapsed = (_time.monotonic() - _t0) * 1000
                        response.raise_for_status()
                        resp_json = response.json()
                        
                        # Aplica o response mapping (extraindo só o essencial)
                        if getattr(mcp, "response_mapping", None):
                            resp_json = _apply_response_mapping(resp_json, mcp.response_mapping)
                        
                        # Log do payload de saída (após mapeamento se houver)
                        logger.info(f"[MCPTool] 📦 PAYLOAD SAÍDA (HTTP): {json.dumps(resp_json, ensure_ascii=False)[:1000]}")
                            
                        resp_preview = json.dumps(resp_json, ensure_ascii=False)[:500]
                        logger.info(
                            f"[MCPTool] ✅ HTTP OK  tool={tool_name!r}  method={method}  "
                            f"status={response.status_code}  elapsed={_elapsed:.0f}ms  "
                            f"response_preview={resp_preview!r}"
                        )
                        return json.dumps(resp_json, indent=2, ensure_ascii=False)
                        
            except Exception as e:
                logger.error(
                    f"[MCPTool] 💥 EXCEPTION  tool={tool_name!r}  error={type(e).__name__}: {e}",
                    exc_info=True
                )
                return json.dumps({"error": str(e)})
        
        return execute_tool
    
    def _schema_to_pydantic(self, schema: Dict[str, Any], tool_name: str) -> type:
        """Convert JSON schema to Pydantic model.
        All fields are exposed to the AI, allowing it to satisfy $fromAI parameters.
        Fallback to context data occurs in execute_tool if the AI leaves them null.
        """
        properties = schema.get("properties", {})
        
        fields = {}
        for prop_name, prop_schema in properties.items():
            if not isinstance(prop_schema, dict):
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
        """Create LangChain tools from an MCP.
        Pre-resolves {{ $request }} placeholders BEFORE presenting tools to the agent.
        """
        cache_key = str(mcp.id)
        
        # Check cache
        if cache_key in self._tool_cache:
            return self._tool_cache[cache_key]
        
        tools = []
        
        # ── Pre-resolve {{ $request }} in MCP templates ──
        # This ensures the agent NEVER sees $request data; only $fromAI remains.
        pre_resolved_templates = {}
        if mcp.protocol != 'mcp':
            from app.context import get_request_context
            import urllib.parse
            raw_ctx = get_request_context() or {}
            # Merge filtered context_data with raw request context (raw takes priority)
            merged_ctx = {**self.context_data, **raw_ctx}
            
            if merged_ctx:
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
                logger.info(f"[MCPTool] 🔑 Pre-resolved $request placeholders for MCP '{mcp.name}'")
        
        try:
            # Discover available tools
            discovered_tools = await self.discover_mcp_tools(mcp)
            
            for tool_def in discovered_tools:
                tool_name = tool_def["name"]
                base_desc = tool_def.get("description", f"Execute {tool_name}")
                
                # If this tool came from a folder, append the folder's description to the LLM
                group_desc = getattr(mcp, "_group_description_context", None)
                if group_desc:
                    description = f"[Pasta/Grupo: {group_desc}] {base_desc}"
                else:
                    description = base_desc
                    
                input_schema = tool_def.get("input_schema", {})
                
                # ALL params the MCP expects (including context ones)
                all_params = list(input_schema.get("properties", {}).keys())
                
                # Pydantic model for LLM (context fields excluded)
                args_schema = self._schema_to_pydantic(input_schema, tool_name)
                
                # Executor knows ALL params so it can fill context
                # Pass pre-resolved templates so $request is already filled
                executor = self._create_tool_executor(
                    mcp_id=str(mcp.id),
                    tool_name=tool_name,
                    protocol=tool_def.get("protocol", "http"),
                    all_params=all_params,
                    pre_resolved_templates=pre_resolved_templates
                )
                
                # Sanitize tool name for provider compatibility
                # (Google AI Studio allows 128, but OpenAI max is 64 chars)
                import re
                safe_name = re.sub(r'[^a-zA-Z0-9_.\-:]', '_', tool_name)
                safe_name = re.sub(r'^[^a-zA-Z_]', '_', safe_name)  # Must start with letter or underscore
                safe_name = re.sub(r'_+', '_', safe_name).strip('_')  # Collapse multiple underscores
                safe_name = safe_name[:64] if safe_name else f"tool_{cache_key[:8]}"
                
                # Create LangChain tool
                tool = StructuredTool.from_function(
                    coroutine=executor,
                    name=safe_name,
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
