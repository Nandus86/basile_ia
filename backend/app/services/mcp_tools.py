"""
MCP Tools Service - Converts MCP tools to LangChain tools for agents
"""
import asyncio
import json
import re
import ast
import os
import uuid
import copy
import urllib.parse
from typing import List, Optional, Dict, Any, Union, Callable
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import logging

from app.models.mcp import MCP
from app.models.agent import Agent, CollaborationStatus
from app.services.mcp_client import MCPClient, execute_mcp_protocol

logger = logging.getLogger(__name__)


def _extract_request_paths(text: str) -> set:
    """Extrai todos os caminhos de {{ $request.path }} em um texto, ignorando filtros e JSONStringify."""
    if not text:
        return set()
    matches = re.finditer(r'\{\{\s*\$request\.(.*?)\s*\}\}', text)
    paths = set()
    for m in matches:
        raw = m.group(1).strip()
        # Remove JSONStringify wrapper if present
        if raw.startswith('JSONStringify'):
            inner_match = re.match(r'JSONStringify\s*\(\s*\$request\.(.+?)\s*\)$', raw)
            if inner_match:
                raw = inner_match.group(1).strip()
        # Pega apenas a parte antes do pipe '|'
        path = raw.split('|')[0].strip()
        paths.add(path)
    return paths


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
    """
    Substitui {{ $request.path }} por valores reais do context_data.
    Suporta filtros: {{ $request.path | truncate(150) }} ou {{ $request.path.truncate(150) }}
    Suporta JSONStringify: {{ JSONStringify($request.path) }} para converter objetos em string JSON
    """
    if not text or not context_data:
        return text
    
    def replacer(match):
        full_match = match.group(0)
        raw = match.group(1).strip()
        
        # Detecta JSONStringify: {{ JSONStringify($request.path) }}
        stringify_match = re.match(r'JSONStringify\s*\(\s*\$request\.(.+?)\s*\)$', raw)
        is_stringify = stringify_match is not None
        if is_stringify:
            path = stringify_match.group(1).strip()
        else:
            path = raw
        
        # Suporta tanto 'path | truncate(N)' quanto 'path.truncate(N)'
        limit = None
        
        # Regex para capturar | truncate(N) ou .truncate(N) no final da string
        # Aceita 'truncate' ou 'limit'
        filter_match = re.search(r'(?:[|.]\s*)(?:truncate|limit)\((\d+)\)$', path)
        if filter_match:
            try:
                limit = int(filter_match.group(1))
                path = path[:filter_match.start()].strip()
            except:
                pass
        
        val = _get_value_by_path(context_data, path)
        
        if val is None:
            return match.group(0)  # Mantém o placeholder se não encontrar
            
        # Converte para string base
        if isinstance(val, bool):
            res = "true" if val else "false"
        elif isinstance(val, (dict, list)):
            res = json.dumps(val, ensure_ascii=False)
        else:
            res = str(val)
        
        # Se JSONStringify foi usado, o resultado já é string JSON (json.dumps já foi aplicado)
        # Não precisamos de tratamento adicional pois já está em formato string
        # O json.dumps já retorna string com aspas duplas internas escapadas
        
        # Aplica limite se extraído
        if limit is not None and not is_stringify:
            if len(res) > limit:
                res = res[:limit].strip() + "..."
        
        return res
            
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


def _parse_group_fields(fields_str: str) -> list:
    """Parse '{field1, alias2: field2, field3}' into [(alias, path)] tuples.
    If no alias is given, uses the last segment of the path as alias.
    Examples:
        '_id, name' -> [('_id','_id'), ('name','name')]
        'id: _id, nome: name' -> [('id','_id'), ('nome','name')]
        '_id, profile.name' -> [('_id','_id'), ('name','profile.name')]
    """
    fields = []
    for part in fields_str.split(','):
        part = part.strip()
        if not part:
            continue
        if ':' in part:
            alias, path = part.split(':', 1)
            fields.append((alias.strip(), path.strip()))
        else:
            # Default alias = last segment of the path
            alias = part.rsplit('.', 1)[-1] if '.' in part else part
            fields.append((alias, part))
    return fields


def _apply_response_mapping(data: dict, mapping: dict) -> dict:
    """Extrai partes de um JSON de resposta profundo e mapeia como especificado pelo admin.
    
    Suporta sintaxe agrupada: "body[*].{_id, name, address}" que retorna
    [{_id, name, address}, ...] ao invés de arrays separados.
    Também suporta renomeação: "body[*].{id: _id, nome: name}".
    """
    if not mapping or not isinstance(mapping, dict):
        return data

    def _apply_limit(val, limit):
        if val is None:
            return None
        if isinstance(val, list):
            return [_apply_limit(item, limit) for item in val]
        if isinstance(val, dict):
            return {k: _apply_limit(v, limit) for k, v in val.items()}
        
        res = str(val)
        if len(res) > limit:
            return res[:limit].strip() + "..."
        return res

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

    def _extract_grouped(source_data, base_path, fields, limit):
        """Extrai campos agrupados de um array, retornando [{alias: val, ...}, ...]"""
        # Resolve o base_path até chegar no array (remove [*] do final)
        # Ex: "body[*]" -> extrai "body", "data.results[*]" -> extrai "data.results"
        array_path = base_path
        if array_path.endswith('[*]'):
            array_path = array_path[:-3]
        if array_path.endswith('.'):
            array_path = array_path[:-1]
        
        source_array = _extract(source_data, array_path) if array_path else source_data
        
        if not isinstance(source_array, list):
            return None
        
        grouped = []
        for item in source_array:
            obj = {}
            for alias, field_path in fields:
                val = _extract(item, field_path)
                if limit is not None:
                    val = _apply_limit(val, limit)
                obj[alias] = val
            grouped.append(obj)
        return grouped

    result = {}
    for key, raw_path in mapping.items():
        if isinstance(raw_path, str):
            path = raw_path.strip()
            limit = None
            
            # Detecta filtro truncate/limit via pipe ou dot notation
            # Ex: "body[*].desc | truncate(150)" ou "body[*].desc.truncate(150)"
            filter_match = re.search(r'(?:[|.]\s*)(?:truncate|limit)\((\d+)\)$', path)
            if filter_match:
                try:
                    limit = int(filter_match.group(1))
                    path = path[:filter_match.start()].strip()
                except:
                    pass
            
            # Detecta sintaxe agrupada: path[*].{field1, field2, alias: field3}
            group_match = re.search(r'\.\{([^}]+)\}$', path)
            if group_match and '[*]' in path:
                fields_str = group_match.group(1)
                fields = _parse_group_fields(fields_str)
                base_path = path[:group_match.start()]  # tudo antes do .{...}
                
                val = _extract_grouped(data, base_path, fields, limit)
            else:
                val = _extract(data, path)
                
                # Aplica o limite se encontrado (suporta listas recursivamente)
                if limit is not None:
                    val = _apply_limit(val, limit)
                
            result[key] = val
        else:
            result[key] = raw_path

    # Filtra apenas os valores que não são None (que foram encontrados)
    filtered_result = {k: v for k, v in result.items() if v is not None}
            
    # Se o mapeamento não resultou em nada útil, devolve o dado original
    # para que o Agente ou UI tenham acesso ao payload completo.
    return filtered_result if filtered_result else data


def _filter_sensitive_response_fields(data: Any) -> Any:
    """Recursively removes common sensitive fields from API responses"""
    sensitive_keys = {
        "bank_details", "password", "token", "apikey", "secret", 
        "auth", "credential", "private", "key"
    }
    
    if isinstance(data, dict):
        new_data = {}
        for k, v in data.items():
            if k.lower() in sensitive_keys:
                continue
            new_data[k] = _filter_sensitive_response_fields(v)
        return new_data
    elif isinstance(data, list):
        return [_filter_sensitive_response_fields(item) for item in data]
    return data


def _truncate_large_response(data: Any, max_len: int = 10000) -> Any:
    """Truncates very large responses to prevent LLM context overflow/crashes"""
    text = json.dumps(data, ensure_ascii=False)
    if len(text) <= max_len:
        return data
        
    # If it's a list, try taking just the first few items
    if isinstance(data, list) and len(data) > 3:
        original_count = len(data)
        truncated_list = data[:3]
        return {
            "items": truncated_list,
            "total_items": original_count,
            "warning": f"Response truncated from {original_count} items to 3 to prevent context overflow."
        }
    
    # If it's a dict with a large body, truncate the body
    if isinstance(data, dict) and "body" in data and isinstance(data["body"], list):
        original_body_count = len(data["body"])
        if original_body_count > 3:
            data["body"] = data["body"][:3]
            data["warning"] = f"Body list truncated from {original_body_count} to 3 items."
            return data

    # Fallback to string truncation if still too big
    return text[:max_len] + "... [TRUNCATED]"


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
    
    # Suggestions should ONLY be from all_params or known $fromAI fields
    # to avoid leaking hidden request context data.
    suggestions = {}
    for null_key in null_keys:
        # Instead of searching flat_context, we just suggest the field is missing
        # if it's part of the expected tool schema.
        pass
    
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
            
            schema_properties = {}
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
        
        # State to track identical calls within this executor's lifecycle (per turn)
        _call_history: Dict[str, Any] = {}
        
        async def execute_tool(**kwargs) -> str:
            from app.context import get_request_context
            import os
            import hashlib
            
            # Simple deduplication: hash kwargs to detect identical repeat calls
            kwargs_hash = hashlib.md5(json.dumps(kwargs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if kwargs_hash in _call_history:
                _calldata = _call_history[kwargs_hash]
                _calldata["count"] += 1
                
                # If called more than 2 times identical, short-circuit
                if _calldata["count"] > 2:
                    logger.warning(f"[MCPTool] 🛑 PREVENTED RECURSION LOOP tool={tool_name!r} args_hash={kwargs_hash} (called {_calldata['count']} times)")
                    # Instead of returning a string that the LLM ignores, we raise an exception
                    # This hard-crashes the local ReAct loop so it skips this tool and proceeds.
                    raise RuntimeError(f"Tool {tool_name} repetida consecutivamente. Execução bloqueada para prevenir loop infinito.")
            else:
                _call_history[kwargs_hash] = {"count": 1, "last_result": None}
            
            
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
                    # Store with both dot and dash notation for compatibility
                    dot_key = ".".join(current_parts)
                    flat_context[dot_key] = value
                    
                    for i in range(len(current_parts)):
                        flat_key = "-".join(current_parts[i:])
                        if flat_key not in flat_context:
                            flat_context[flat_key] = value
                    if isinstance(value, dict):
                        flatten_dict(value, current_parts)
            
            if context:
                flatten_dict(context)

            # ── Dynamic Fallback for {{ $request }} ──
            # If templates still have placeholders, try resolving them NOW
            # (Safety net if pre-resolution during creation failed due to missing context)
            _final_templates = _pre_resolved.copy()
            for key in ['endpoint_str', 'body_str', 'headers_str', 'query_str']:
                val = _final_templates.get(key)
                if val and '{{' in val and '$request' in val:
                    _final_templates[key] = _inject_request_params(val, context)
            
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
                        logger.info(f"[MCPTool] 📦 PAYLOAD SAÍDA (MCP raw): {json.dumps(res_data, ensure_ascii=False)[:1000]}")
                        
                        # Aplica response_mapping (mesmo tratamento que HTTP)
                        if getattr(mcp, "response_mapping", None):
                            res_data = _apply_response_mapping(res_data, mcp.response_mapping)
                        
                        # Apply safe filtering and truncation (mesmo que HTTP)
                        res_data = _filter_sensitive_response_fields(res_data)
                        res_data = _truncate_large_response(res_data)
                        
                        raw = json.dumps(res_data, indent=2, ensure_ascii=False)
                        logger.info(
                            f"[MCPTool] ✅ MCP OK  tool={tool_name!r}  "
                            f"elapsed={_elapsed:.0f}ms  response_preview={raw[:500]!r}"
                        )
                        _call_history[kwargs_hash]["last_result"] = raw
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

                    # Resolve global macros like {{ $now }}
                    from app.utils.macros import resolve_global_macros
                    body_str = resolve_global_macros(body_str, context)
                    headers_str = resolve_global_macros(headers_str, context)
                    query_str = resolve_global_macros(query_str, context)
                    endpoint_str = resolve_global_macros(endpoint_str, context)

                    used_all.update(u_body, u_headers, u_query, u_endpoint)
                    
                    body = json.loads(body_str)
                    headers = json.loads(headers_str)
                    query = json.loads(query_str)
                    
                    # Legacy behavior: Include explicit 'params' object passed by the LLM
                    # (Only if it was explicitly defined in the schema, which it isn't anymore by default)
                    if "params" in final_args and isinstance(final_args["params"], dict):
                        if mcp.method.upper() == "GET":
                            query.update(final_args["params"])
                        else:
                            body.update(final_args["params"])
                    
                    # IMPORTANT: We NO LONGER forward remaining non-macro args into body/query
                    # to prevent information leakage from context_data.
                    # Only fields explicitly in the template or AI-provided params are sent.
                    
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
                        # Apply safe filtering and truncation to prevent leaks and crashes
                        filtered_json = _filter_sensitive_response_fields(resp_json)
                        safe_json = _truncate_large_response(filtered_json)
                        
                        final_res = json.dumps(safe_json, indent=2, ensure_ascii=False)
                        _call_history[kwargs_hash]["last_result"] = final_res
                        return final_res
                        
            except Exception as e:
                logger.error(
                    f"[MCPTool] 💥 EXCEPTION  tool={tool_name!r}  error={type(e).__name__}: {e}",
                    exc_info=True
                )
                err_res = json.dumps({"error": str(e)})
                _call_history[kwargs_hash]["last_result"] = err_res
                return err_res
        
        return execute_tool
    
    def _schema_to_pydantic(self, schema: Dict[str, Any], tool_name: str, exclude_props: Optional[set] = None) -> type:
        """Convert JSON schema to Pydantic model.
        Excludes properties that are satisfied by $request (system) to reduce AI token bloat.
        """
        properties = schema.get("properties", {})
        exclude_props = exclude_props or set()
        
        fields = {}
        for prop_name, prop_schema in properties.items():
            if not isinstance(prop_schema, dict) or prop_name in exclude_props:
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

                # Identify props that are actually $request to exclude them from AI model
                request_props = set()
                # 1. Identify by $request in template strings (Dynamic discovery)
                mcp_endpoint_raw = getattr(mcp, "endpoint", "") or ""
                mcp_body_raw = json.dumps(mcp.body_template or {})
                mcp_headers_raw = json.dumps(mcp.headers or {})
                mcp_query_raw = json.dumps(getattr(mcp, "query_template", {}) or {})
                
                for t_val in [mcp_endpoint_raw, mcp_body_raw, mcp_headers_raw, mcp_query_raw]:
                    if t_val:
                        request_props.update(_extract_request_paths(t_val))

                # 2. Check properties whose name or description indicates it's context-filled
                for p_name, p_schema in input_schema.get("properties", {}).items():
                    desc = str(p_schema.get("description", "")).lower()
                    if "$request" in desc or p_name in request_props:
                        request_props.add(p_name)

                # Pydantic model for LLM (context fields excluded)
                args_schema = self._schema_to_pydantic(input_schema, tool_name, exclude_props=request_props)
                
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


async def get_agent_mcp_metadata(db: AsyncSession, agent_id: str) -> Dict[str, Any]:
    """
    Descobre metadados de todos os MCPs de um agente (campos $request e $fromAI).
    Útil para filtrar o contexto do Agente de forma ultra-estrita.
    """
    executor = MCPToolExecutor(db)
    mcps = await executor.get_agent_mcps(agent_id)
    
    metadata = {
        "request_paths": set(),
        "from_ai_names": set()
    }
    
    # Process agent's own MCPs
    _extract_metadata_from_mcps(mcps, metadata)
    
    # RECURSIVE: If agent is orchestrator, also collect metadata from collaborators
    # to allow pruning their $request fields from the orchestrator's prompt.
    from sqlalchemy import select
    from app.models.agent import Agent, AgentCollaborator, CollaborationStatus
    
    import uuid
    try:
        agent_uuid = uuid.UUID(agent_id)
    except ValueError:
        return metadata
        
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(Agent)
        .options(selectinload(Agent.collaborator_settings))
        .where(Agent.id == agent_uuid)
    )
    agent = result.scalar_one_or_none()
    
    if agent and getattr(agent, "is_orchestrator", False):
            for collab_rel in agent.collaborator_settings:
                if collab_rel.status != CollaborationStatus.BLOCKED:
                    sub_executor = MCPToolExecutor(db)
                    sub_mcps = await sub_executor.get_agent_mcps(str(collab_rel.collaborator_id))
                    _extract_metadata_from_mcps(sub_mcps, metadata)
            
    return metadata


def _extract_metadata_from_mcps(mcps: List[MCP], metadata: Dict[str, Any]):
    """Helper to extract metadata from a list of MCPs"""
    import urllib.parse
    for mcp in mcps:
        templates = [
            urllib.parse.unquote(mcp.endpoint or ""),
            json.dumps(mcp.headers or {}),
            json.dumps(mcp.body_template or {}),
            json.dumps(getattr(mcp, "query_template", {}) or {})
        ]
        
        for t in templates:
            metadata["request_paths"].update(_extract_request_paths(t))
            ai_params = _extract_from_ai_params(t)
            metadata["from_ai_names"].update(ai_params.keys())

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
