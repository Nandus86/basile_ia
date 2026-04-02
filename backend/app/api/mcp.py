"""
MCP CRUD and Execution Endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, AsyncGenerator
from uuid import UUID
import httpx
import time
import json
import asyncio

from app.database import get_db
from app.models.mcp import MCP
from app.schemas.mcp import (
    MCPCreate, MCPUpdate, MCPResponse, MCPList,
    MCPExecuteRequest, MCPExecuteResponse
)
from app.services.mcp_client import execute_mcp_protocol

router = APIRouter()


@router.get("", response_model=MCPList)
async def list_mcps(
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = None,
    protocol: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """List all MCPs with optional filtering"""
    query = select(MCP)
    
    if is_active is not None:
        query = query.where(MCP.is_active == is_active)
    
    if protocol is not None:
        query = query.where(MCP.protocol == protocol)
    
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    mcps = result.scalars().all()
    
    # Count total
    count_query = select(MCP)
    if is_active is not None:
        count_query = count_query.where(MCP.is_active == is_active)
    if protocol is not None:
        count_query = count_query.where(MCP.protocol == protocol)
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())
    
    return MCPList(mcps=mcps, total=total)


@router.get("/{mcp_id}", response_model=MCPResponse)
async def get_mcp(
    mcp_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific MCP by ID"""
    result = await db.execute(
        select(MCP).where(MCP.id == mcp_id)
    )
    mcp = result.scalar_one_or_none()
    
    if not mcp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MCP not found"
        )
    
    return mcp


@router.post("", response_model=MCPResponse, status_code=status.HTTP_201_CREATED)
async def create_mcp(
    mcp_data: MCPCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new MCP"""
    mcp = MCP(**mcp_data.model_dump())
    db.add(mcp)
    await db.commit()
    await db.refresh(mcp)
    
    return mcp


@router.put("/{mcp_id}", response_model=MCPResponse)
async def update_mcp(
    mcp_id: UUID,
    mcp_data: MCPUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update an existing MCP"""
    result = await db.execute(
        select(MCP).where(MCP.id == mcp_id)
    )
    mcp = result.scalar_one_or_none()
    
    if not mcp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MCP not found"
        )
    
    # Update only provided fields
    update_data = mcp_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(mcp, field, value)
    
    await db.commit()
    await db.refresh(mcp)
    
    return mcp


@router.delete("/{mcp_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp(
    mcp_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete an MCP"""
    result = await db.execute(
        select(MCP).where(MCP.id == mcp_id)
    )
    mcp = result.scalar_one_or_none()
    
    if not mcp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MCP not found"
        )
    
    await db.delete(mcp)
    await db.commit()


from app.services.mcp_tools import _inject_from_ai_params, _apply_response_mapping, _inject_request_params
import urllib.parse


def _unflatten_dot_paths(flat: dict) -> dict:
    """Converts flat dot-path keys into nested dicts.
    e.g. {'system.baseUrlBasileia': 'https://...'} -> {'system': {'baseUrlBasileia': 'https://...'}}
    """
    result = {}
    for key, value in flat.items():
        parts = key.split('.')
        d = result
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        d[parts[-1]] = value
    return result


async def execute_http(mcp: MCP, request_params: dict, timeout: float, variables: dict = None) -> dict:
    """Execute standard HTTP request"""
    # Build safely injected params
    body_str = json.dumps(mcp.body_template or {})
    headers_str = json.dumps(mcp.headers or {})
    endpoint_str = urllib.parse.unquote(mcp.endpoint or "")
    query_str = json.dumps(getattr(mcp, "query_template", {}) or {})
    
    # First resolve {{ $request.xxx }} using test variables (if provided)
    if variables:
        test_ctx = _unflatten_dot_paths(variables)
        endpoint_str = _inject_request_params(endpoint_str, test_ctx)
        body_str = _inject_request_params(body_str, test_ctx)
        headers_str = _inject_request_params(headers_str, test_ctx)
        query_str = _inject_request_params(query_str, test_ctx)
    
    body_str, _ = _inject_from_ai_params(body_str, request_params)
    headers_str, _ = _inject_from_ai_params(headers_str, request_params)
    endpoint_str, _ = _inject_from_ai_params(endpoint_str, request_params)
    query_str, _ = _inject_from_ai_params(query_str, request_params)
    
    body = json.loads(body_str)
    headers = json.loads(headers_str)
    query = json.loads(query_str)
    
    # Merge remaining test parameters into body or query
    for k, v in request_params.items():
        if mcp.method.upper() == "GET":
            if k not in query:
                query[k] = v
        else:
            if k not in body:
                body[k] = v
                
    safe_headers = {}
    for hk, hv in headers.items():
        safe_headers[str(hk).encode("utf-8")] = str(hv).encode("utf-8")

    # [Log de Entrada]
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[MCP API] 📤 ENTRADA (HTTP) endpoint={endpoint_str} method={mcp.method.upper()}: body={json.dumps(body, ensure_ascii=False)} query={json.dumps(query, ensure_ascii=False)}")

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        if mcp.method.upper() == "GET":
            response = await client.get(
                endpoint_str,
                headers=safe_headers,
                params=query
            )
        elif mcp.method.upper() == "POST":
            response = await client.post(
                endpoint_str,
                headers=safe_headers,
                params=query,
                json=body
            )
        elif mcp.method.upper() == "PUT":
            response = await client.put(
                endpoint_str,
                headers=safe_headers,
                params=query,
                json=body
            )
        elif mcp.method.upper() == "PATCH":
            response = await client.patch(
                endpoint_str,
                headers=safe_headers,
                params=query,
                json=body
            )
        elif mcp.method.upper() == "DELETE":
            response = await client.delete(
                endpoint_str,
                headers=safe_headers,
                params=query
            )
        else:
            raise ValueError(f"Unsupported method: {mcp.method}")
        
        response.raise_for_status()
        resp_json = response.json()
        
        # Aplica o response mapping para o teste da UI bater com o Agente
        if getattr(mcp, "response_mapping", None):
            resp_json = _apply_response_mapping(resp_json, mcp.response_mapping)
        
        # Log do payload de saída (Dashboard/API)
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[MCP API] 📦 PAYLOAD SAÍDA (HTTP): {json.dumps(resp_json, ensure_ascii=False)[:1000]}")
            
        return resp_json


async def execute_sse(mcp: MCP, request_params: dict, timeout: float, variables: dict = None) -> dict:
    """Execute SSE (Server-Sent Events) request and collect all events"""
    events = []
    final_result = None
    
    # Build safely injected params
    body_str = json.dumps(mcp.body_template or {})
    headers_str = json.dumps(mcp.headers or {})
    endpoint_str = urllib.parse.unquote(mcp.endpoint or "")
    query_str = json.dumps(getattr(mcp, "query_template", {}) or {})
    
    # First resolve {{ $request.xxx }} using test variables (if provided)
    if variables:
        test_ctx = _unflatten_dot_paths(variables)
        endpoint_str = _inject_request_params(endpoint_str, test_ctx)
        body_str = _inject_request_params(body_str, test_ctx)
        headers_str = _inject_request_params(headers_str, test_ctx)
        query_str = _inject_request_params(query_str, test_ctx)
    
    body_str, _ = _inject_from_ai_params(body_str, request_params)
    headers_str, _ = _inject_from_ai_params(headers_str, request_params)
    endpoint_str, _ = _inject_from_ai_params(endpoint_str, request_params)
    query_str, _ = _inject_from_ai_params(query_str, request_params)
    
    body = json.loads(body_str)
    headers = json.loads(headers_str)
    query = json.loads(query_str)
    
    # Merge remaining test parameters into body or query
    for k, v in request_params.items():
        if mcp.method.upper() == "GET":
            if k not in query:
                query[k] = v
        else:
            if k not in body:
                body[k] = v
                
    safe_headers = {**headers, "Accept": "text/event-stream", "Cache-Control": "no-cache"}
    for hk, hv in list(safe_headers.items()):
        safe_headers[str(hk).encode("utf-8")] = str(hv).encode("utf-8")
    
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        async with client.stream(
            mcp.method.upper(),
            endpoint_str,
            headers=safe_headers,
            json=body if mcp.method.upper() != "GET" else None,
            params=query if mcp.method.upper() == "GET" else None
        ) as response:
            response.raise_for_status()
            
            current_event = {"event": "message", "data": ""}
            
            async for line in response.aiter_lines():
                line = line.strip()
                
                if not line:
                    # Empty line means end of event
                    if current_event["data"]:
                        try:
                            parsed_data = json.loads(current_event["data"])
                            event_obj = {
                                "type": current_event["event"],
                                "data": parsed_data
                            }
                            events.append(event_obj)
                            final_result = parsed_data
                        except json.JSONDecodeError:
                            events.append({
                                "type": current_event["event"],
                                "data": current_event["data"]
                            })
                            final_result = current_event["data"]
                    current_event = {"event": "message", "data": ""}
                elif line.startswith("event:"):
                    current_event["event"] = line[6:].strip()
                elif line.startswith("data:"):
                    data_part = line[5:].strip()
                    if current_event["data"]:
                        current_event["data"] += "\n" + data_part
                    else:
                        current_event["data"] = data_part
                elif line.startswith("id:"):
                    current_event["id"] = line[3:].strip()
    
    return {
        "events": events,
        "result": final_result,
        "event_count": len(events)
    }


async def stream_sse(mcp: MCP, body: dict, timeout: float) -> AsyncGenerator[str, None]:
    """Stream SSE events as they arrive"""
    # Log do payload de entrada (parâmetros da UI)
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[MCP API] 📤 PAYLOAD ENTRADA (HTTP): body={json.dumps(body, ensure_ascii=False)}")
        
    async with httpx.AsyncClient(timeout=timeout) as client:
        headers = {**mcp.headers}
        headers["Accept"] = "text/event-stream"
        headers["Cache-Control"] = "no-cache"
        
        # [Log de Entrada]
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[MCP API] 📤 ENTRADA (STREAM) endpoint={mcp.endpoint}: body={json.dumps(body, ensure_ascii=False)}")
        
        async with client.stream(
            mcp.method.upper(),
            mcp.endpoint,
            headers=headers,
            json=body if mcp.method.upper() != "GET" else None,
            params=body if mcp.method.upper() == "GET" else None
        ) as response:
            response.raise_for_status()
            
            async for line in response.aiter_lines():
                yield line + "\n"


@router.post("/{mcp_id}/execute", response_model=MCPExecuteResponse)
async def execute_mcp(
    mcp_id: UUID,
    request: MCPExecuteRequest,
    db: AsyncSession = Depends(get_db)
):
    """Execute an MCP with given parameters"""
    start_time = time.time()
    
    # Get MCP
    result = await db.execute(
        select(MCP).where(MCP.id == mcp_id)
    )
    mcp = result.scalar_one_or_none()
    
    if not mcp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MCP not found"
        )
    
    if not mcp.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MCP is not active"
        )
    
    try:
        # Build request body from template
        body = {**mcp.body_template}
        for key, value in request.params.items():
            body[key] = value
        
        # Get timeout
        timeout = float(mcp.timeout_seconds or 30)
        
        # Execute based on protocol
        protocol = (mcp.protocol or "http").lower()
        
        if protocol == "http":
            result_data = await execute_http(mcp, request.params, timeout, variables=request.variables or {})
            events = None
        elif protocol == "sse":
            sse_result = await execute_sse(mcp, request.params, timeout, variables=request.variables or {})
            result_data = sse_result.get("result")
            events = sse_result.get("events")
        elif protocol == "mcp":
            # Full MCP Protocol (bidirectional)
            # Extract query params from body_template (like user_id)
            query_params = {}
            for key in ["user_id", "session_id"]:
                if key in body:
                    query_params[key] = body.pop(key)
            
            # Default action is list_tools, can be overridden via params
            action = request.params.get("_action", "list_tools")
            tool_name = request.params.get("_tool_name")
            tool_args = {k: v for k, v in request.params.items() if not k.startswith("_")}
            
            # Log do payload de entrada (parâmetros da UI MCP Protocol)
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"[MCP API] 📤 PAYLOAD ENTRADA (MCP): action={action} tool={tool_name} args={json.dumps(tool_args, ensure_ascii=False)}")
                
            mcp_result = await execute_mcp_protocol(
                endpoint=mcp.endpoint,
                headers=mcp.headers or {},
                query_params=query_params,
                action=action,
                tool_name=tool_name,
                tool_args=tool_args if tool_args else None,
                timeout=timeout
            )
            
            result_data = mcp_result.get("result")
            events = mcp_result.get("events")
            
            if not mcp_result.get("success"):
                raise Exception(mcp_result.get("error", "MCP execution failed"))

            # Log do payload de saída (Dashboard/API MCP Protocol)
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"[MCP API] 📦 SAÍDA (MCP): {json.dumps(result_data, ensure_ascii=False)[:1000]}")
                
        elif protocol == "websocket":
            # WebSocket not fully implemented yet
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="WebSocket protocol not yet implemented"
            )
        elif protocol == "stdio":
            # STDIO not fully implemented yet
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="STDIO protocol not yet implemented"
            )
        else:
            raise ValueError(f"Unsupported protocol: {protocol}")
        
        execution_time = (time.time() - start_time) * 1000
        
        return MCPExecuteResponse(
            success=True,
            result=result_data,
            execution_time_ms=execution_time,
            events=events
        )
        
    except Exception as e:
        execution_time = (time.time() - start_time) * 1000
        return MCPExecuteResponse(
            success=False,
            error=str(e),
            execution_time_ms=execution_time
        )


@router.post("/{mcp_id}/stream")
async def stream_mcp(
    mcp_id: UUID,
    request: MCPExecuteRequest,
    db: AsyncSession = Depends(get_db)
):
    """Stream SSE events from an MCP (for real-time streaming)"""
    # Get MCP
    result = await db.execute(
        select(MCP).where(MCP.id == mcp_id)
    )
    mcp = result.scalar_one_or_none()
    
    if not mcp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MCP not found"
        )
    
    if not mcp.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MCP is not active"
        )
    
    protocol = (mcp.protocol or "http").lower()
    if protocol != "sse":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stream endpoint only works with SSE protocol MCPs"
        )
    
    # Build request body
    body = {**mcp.body_template}
    for key, value in request.params.items():
        body[key] = value
    
    timeout = float(mcp.timeout_seconds or 30)
    
    return StreamingResponse(
        stream_sse(mcp, body, timeout),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/{mcp_id}/tools", response_model=MCPExecuteResponse)
async def list_mcp_tools(
    mcp_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """List available tools from an MCP server (MCP Protocol only)"""
    start_time = time.time()
    
    # Get MCP
    result = await db.execute(
        select(MCP).where(MCP.id == mcp_id)
    )
    mcp = result.scalar_one_or_none()
    
    if not mcp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MCP not found"
        )
    
    if not mcp.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MCP is not active"
        )
    
    protocol = (mcp.protocol or "http").lower()
    if protocol != "mcp":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tools endpoint only works with MCP protocol"
        )
    
    try:
        # Extract query params from body_template
        query_params = {}
        body = {**mcp.body_template}
        for key in ["user_id", "session_id"]:
            if key in body:
                query_params[key] = body.pop(key)
        
        timeout = float(mcp.timeout_seconds or 60)
        
        mcp_result = await execute_mcp_protocol(
            endpoint=mcp.endpoint,
            headers=mcp.headers or {},
            query_params=query_params,
            action="list_tools",
            timeout=timeout
        )
        
        execution_time = (time.time() - start_time) * 1000
        
        return MCPExecuteResponse(
            success=mcp_result.get("success", False),
            result=mcp_result.get("result"),
            error=mcp_result.get("error"),
            execution_time_ms=execution_time,
            events=mcp_result.get("events")
        )
        
    except Exception as e:
        execution_time = (time.time() - start_time) * 1000
        return MCPExecuteResponse(
            success=False,
            error=str(e),
            execution_time_ms=execution_time
        )


from pydantic import BaseModel
from typing import Dict, Any

class MCPToolCallRequest(BaseModel):
    """Request to call a specific MCP tool"""
    tool_name: str
    arguments: Dict[str, Any] = {}


@router.post("/{mcp_id}/tools/call", response_model=MCPExecuteResponse)
async def call_mcp_tool(
    mcp_id: UUID,
    request: MCPToolCallRequest,
    db: AsyncSession = Depends(get_db)
):
    """Execute a specific tool on an MCP server"""
    start_time = time.time()
    
    # Get MCP
    result = await db.execute(
        select(MCP).where(MCP.id == mcp_id)
    )
    mcp = result.scalar_one_or_none()
    
    if not mcp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MCP not found"
        )
    
    if not mcp.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MCP is not active"
        )
    
    protocol = (mcp.protocol or "http").lower()
    if protocol != "mcp":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tool call endpoint only works with MCP protocol"
        )
    
    try:
        # Extract query params from body_template
        query_params = {}
        body = {**mcp.body_template}
        for key in ["user_id", "session_id"]:
            if key in body:
                query_params[key] = body.pop(key)
        
        timeout = float(mcp.timeout_seconds or 60)
        
        # [Log de Entrada]
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[MCP API] 📤 ENTRADA (TOOL CALL) tool={request.tool_name}: {json.dumps(request.arguments, ensure_ascii=False)}")
        
        mcp_result = await execute_mcp_protocol(
            endpoint=mcp.endpoint,
            headers=mcp.headers or {},
            query_params=query_params,
            action="call_tool",
            tool_name=request.tool_name,
            tool_args=request.arguments,
            timeout=timeout
        )
        
        execution_time = (time.time() - start_time) * 1000
        
        # [Log de Saída]
        logger.info(f"[MCP API] 📦 SAÍDA (TOOL CALL) tool={request.tool_name}: {json.dumps(mcp_result.get('result'), ensure_ascii=False)[:1000]}")
        
        return MCPExecuteResponse(
            success=mcp_result.get("success", False),
            result=mcp_result.get("result"),
            error=mcp_result.get("error"),
            execution_time_ms=execution_time,
            events=mcp_result.get("events")
        )
        
    except Exception as e:
        execution_time = (time.time() - start_time) * 1000
        return MCPExecuteResponse(
            success=False,
            error=str(e),
            execution_time_ms=execution_time
        )
