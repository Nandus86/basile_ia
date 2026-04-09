from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
import httpx
from pydantic import BaseModel

from app.config import settings

router = APIRouter()

async def _proxy(method: str, path: str, request: Request, body_json: dict = None):
    """Generic HTTP Proxy helper."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{settings.DISPARADOR_SERVICE_URL}{path}"
        headers = dict(request.headers)
        # Drop host so httpx sets it to the target host
        headers.pop("host", None)
        
        try:
            if method.lower() == "get":
                resp = await client.request(method, url, headers=headers, params=request.query_params)
            else:
                resp = await client.request(method, url, headers=headers, params=request.query_params, json=body_json)
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"Error communicating with Disparador service: {str(e)}")
            
        try:
            content = resp.json()
        except Exception:
            content = resp.text
            
        return JSONResponse(content=content, status_code=resp.status_code)

@router.post("/webhook/{path:path}")
async def proxy_webhook(path: str, request: Request):
    """Proxy incoming webhook payloads to the Disparador service."""
    body_json = await request.json()
    return await _proxy("POST", f"/webhook/{path}", request, body_json)

@router.get("/dashboard/stats")
async def proxy_dashboard_stats(request: Request):
    return await _proxy("GET", "/dashboard/stats", request)

@router.get("/dashboard/campaigns")
async def proxy_dashboard_campaigns(request: Request):
    return await _proxy("GET", "/dashboard/campaigns", request)

@router.get("/dashboard/campaigns/{service_id}")
async def proxy_dashboard_campaign_details(service_id: str, request: Request):
    return await _proxy("GET", f"/dashboard/campaigns/{service_id}", request)

@router.post("/campaigns/{service_id}/pause")
async def proxy_pause_campaign(service_id: str, request: Request):
    return await _proxy("POST", f"/campaigns/{service_id}/pause", request)

@router.post("/campaigns/{service_id}/resume")
async def proxy_resume_campaign(service_id: str, request: Request):
    return await _proxy("POST", f"/campaigns/{service_id}/resume", request)

@router.post("/campaigns/{service_id}/retry-dlq")
async def proxy_retry_dlq(service_id: str, request: Request):
    return await _proxy("POST", f"/campaigns/{service_id}/retry-dlq", request)

@router.get("/dashboard/campaigns/{service_id}/report")
async def proxy_campaign_report(service_id: str, request: Request):
    return await _proxy("GET", f"/dashboard/campaigns/{service_id}/report", request)
