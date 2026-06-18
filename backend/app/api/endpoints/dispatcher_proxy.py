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
async def proxy_webhook(path: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Proxy incoming webhook payloads to the Disparador service and log the capture."""
    body_json = await request.json()
    
    # Extract contact count
    contact_count = 0
    if isinstance(body_json, dict) and "contacts" in body_json:
        contacts = body_json["contacts"]
        if isinstance(contacts, list):
            contact_count = len(contacts)
            
    # Create initial log entry
    log_entry = DispatcherWebhookLog(
        webhook_path=path,
        status="pending",
        request_payload=body_json,
        contact_count=contact_count
    )
    db.add(log_entry)
    await db.commit()
    await db.refresh(log_entry)
    
    start_time = time.time()
    try:
        # Proxy to disparador (note: we proxy to trigger/personalizado/path internally)
        proxy_response = await _proxy("POST", f"/webhook/trigger/personalizado/{path}", request, body_json)
        duration_ms = int((time.time() - start_time) * 1000)
        
        status_code = proxy_response.status_code
        response_data = None
        try:
            response_data = json.loads(proxy_response.body.decode('utf-8'))
        except Exception:
            response_data = {"text": proxy_response.body.decode('utf-8', errors='replace')}
            
        log_entry.status_code = status_code
        log_entry.duration_ms = duration_ms
        log_entry.response_payload = response_data
        
        if status_code >= 400:
            if status_code == 422:
                log_entry.status = "validation_error"
            elif status_code == 403:
                log_entry.status = "unauthorized"
            else:
                log_entry.status = "failed"
            
            error_msg = None
            if isinstance(response_data, dict):
                error_msg = response_data.get("detail") or response_data.get("message")
            if not error_msg:
                error_msg = str(response_data)
            log_entry.error_message = error_msg
        else:
            log_entry.status = "success"
            
        await db.commit()
        return proxy_response
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        log_entry.status = "failed"
        log_entry.status_code = 500
        log_entry.error_message = str(e)
        log_entry.duration_ms = duration_ms
        await db.commit()
        raise

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

