from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
import httpx
from pydantic import BaseModel
import time
import json
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.dispatcher_webhook_log import DispatcherWebhookLog

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
    """Proxy incoming webhook payloads to the Disparador service without intercepting or logging."""
    body_json = await request.json()
    return await _proxy("POST", f"/webhook/trigger/personalizado/{path}", request, body_json)

# ── Dashboard GET routes ──────────────────────────────────────────────

@router.get("/dashboard/stats")
async def proxy_dashboard_stats(request: Request):
    return await _proxy("GET", "/dashboard/stats", request)

@router.get("/dashboard/campaigns")
async def proxy_dashboard_campaigns(request: Request):
    return await _proxy("GET", "/dashboard/campaigns", request)

@router.get("/dashboard/campaigns/{service_id}")
async def proxy_dashboard_campaign_details(service_id: str, request: Request):
    return await _proxy("GET", f"/dashboard/campaigns/{service_id}", request)

@router.get("/dashboard/campaigns/{service_id}/report")
async def proxy_campaign_report(service_id: str, request: Request):
    return await _proxy("GET", f"/dashboard/campaigns/{service_id}/report", request)

@router.get("/dashboard/staged")
async def proxy_staged_queues(request: Request):
    return await _proxy("GET", "/dashboard/staged", request)

# ── Dashboard POST action routes ─────────────────────────────────────

@router.post("/dashboard/campaigns/{service_id}/pause")
async def proxy_pause_campaign(service_id: str, request: Request):
    return await _proxy("POST", f"/dashboard/campaigns/{service_id}/pause", request)

@router.post("/dashboard/campaigns/{service_id}/resume")
async def proxy_resume_campaign(service_id: str, request: Request):
    return await _proxy("POST", f"/dashboard/campaigns/{service_id}/resume", request)

@router.post("/dashboard/campaigns/{service_id}/activate")
async def proxy_activate_campaign(service_id: str, request: Request):
    return await _proxy("POST", f"/dashboard/campaigns/{service_id}/activate", request)

@router.post("/dashboard/campaigns/{service_id}/retry-dlq")
async def proxy_retry_dlq(service_id: str, request: Request):
    return await _proxy("POST", f"/dashboard/campaigns/{service_id}/retry-dlq", request)

@router.post("/dashboard/campaigns/{service_id}/recreate")
async def proxy_recreate_campaign(service_id: str, request: Request):
    body_json = None
    try:
        body_json = await request.json()
    except Exception:
        pass
    return await _proxy("POST", f"/dashboard/campaigns/{service_id}/recreate", request, body_json)

@router.post("/dashboard/campaigns/{service_id}/delete")
async def proxy_delete_campaign(service_id: str, request: Request):
    return await _proxy("POST", f"/dashboard/campaigns/{service_id}/delete", request)

@router.post("/dashboard/campaigns/{service_id}/redispatch-contact")
async def proxy_redispatch_contact(service_id: str, request: Request):
    body_json = await request.json()
    return await _proxy("POST", f"/dashboard/campaigns/{service_id}/redispatch-contact", request, body_json)

@router.post("/dashboard/campaigns/unlock")
async def proxy_unlock_campaign(request: Request):
    body_json = await request.json()
    return await _proxy("POST", "/dashboard/campaigns/unlock", request, body_json)

@router.post("/dashboard/campaigns/lock")
async def proxy_lock_campaign(request: Request):
    body_json = await request.json()
    return await _proxy("POST", "/dashboard/campaigns/lock", request, body_json)

