"""
Webhook Receive Endpoint — Normalizes, forwards, and queues on failure
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

logger = logging.getLogger(__name__)

from app.database import get_db
from app.models.pipeline import WebhookPipeline
from app.schemas.pipeline import WebhookReceivedResponse, TestWebhookRequest, TestWebhookResponse
from app.services.webhook_processor import normalize_webhook_payload, validate_pipeline_auth
from app.services.queue_publisher import enqueue_for_retry, save_job_status
from app.services.http_forwarder import forwarder
from app.services.workflow_caller import workflow_caller


router = APIRouter()


@router.post("/{path}", response_model=WebhookReceivedResponse)
async def receive_webhook(
    path: str,
    request: Request,
    x_api_key: str = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db)
):
    """
    1. Normalize incoming payload via input_schema
    2. Try to forward to output_url (worker)
    3. If worker is down → store in Redis queue for background retry
    """
    import time
    from app.models.ingress_log import IngressLog

    start_time = time.time()
    payload = {}
    worker_payload = None
    status = "pending"
    error_msg = None
    response_code = None
    response_body = None
    pipeline_obj = None
    dest_url = None

    try:
        try:
            payload = await request.json()
        except Exception:
            payload = {}

        # ── Find pipeline ──
        query = select(WebhookPipeline).where(
            WebhookPipeline.path == path,
            WebhookPipeline.is_active == True
        )
        result = await db.execute(query)
        pipeline = result.scalar_one_or_none()
        pipeline_obj = pipeline

        if not pipeline:
            status = "not_found"
            raise HTTPException(status_code=404, detail="Pipeline not found or inactive")

        dest_url = pipeline.output_url

        if not validate_pipeline_auth(pipeline.auth_type, pipeline.auth_token, x_api_key):
            status = "unauthorized"
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

        # ── Normalize ──
        try:
            normalized = normalize_webhook_payload(
                payload,
                pipeline.input_schema or {},
                path
            )
        except ValueError as e:
            logger.error(f"Validation error in webhook payload for path '{path}': {e}. Payload: {payload}")
            status = "validation_error"
            error_msg = str(e)
            raise HTTPException(status_code=400, detail=str(e))

        job_id = normalized["job_id"]

        # ── Build worker-compatible payload ──
        # If no mappings are defined, do a pass-through of all fields from normalized (which has the original payload)
        mappings = (pipeline.input_schema or {}).get("mappings", {})
        if not mappings:
            worker_payload = dict(normalized)
        else:
            worker_payload = {
                "message": normalized.get("message", ""),
                "session_id": normalized.get("session_id", ""),
            }
            for key in ("agent_id", "user_access_level", "context_data", "transition_data"):
                val = normalized.get(key)
                if val is not None:
                    worker_payload[key] = val
                
        # Resolve callback
        callback_url = normalized.get("callback_url") or pipeline.default_callback_url
        egress_path = normalized.get("egress_pipeline_path") or pipeline.egress_pipeline_path
        
        if egress_path:
            worker_payload["pipeline_path"] = egress_path
            # If user provided an egress path but no explicit callback, point to the internal Egress service
            if not callback_url:
                # Assumes Egress runs on egress-api or accessible via gateway
                callback_url = f"http://basile-egress:8000/egress-api/result?pipeline_path={egress_path}"
                
        if callback_url:
            worker_payload["callback_url"] = callback_url

        # ── Execute Workflow (if enabled) ──
        if pipeline.workflow_enabled and pipeline.workflow_id:
            logger.info(
                f"[Webhook] Executing workflow {pipeline.workflow_id} "
                f"for pipeline '{path}'"
            )
            wf_success, wf_result, wf_error = await workflow_caller.execute(
                pipeline.workflow_id, worker_payload
            )
            if wf_success and wf_result:
                if isinstance(wf_result, dict):
                    # Replace: use only the workflow result as the payload
                    worker_payload = wf_result
                logger.info(
                    f"[Webhook] Workflow result applied as payload "
                    f"for pipeline '{path}'"
                )
            else:
                # Fallback: continue with original payload on workflow failure
                logger.warning(
                    f"[Webhook] Workflow failed for pipeline '{path}': "
                    f"{wf_error}. Continuing with original payload."
                )
                error_msg = f"Workflow error: {wf_error}"

        # Sanitize standard fields to avoid 422 errors on the worker/backend side
        if worker_payload.get("message") is None:
            worker_payload["message"] = ""
        if not worker_payload.get("session_id"):
            import uuid
            worker_payload["session_id"] = f"session_{uuid.uuid4().hex[:8]}"
        if "user_access_level" in worker_payload and worker_payload["user_access_level"] is None:
            worker_payload["user_access_level"] = "normal"

        # ── Try to forward immediately ──
        output_url = pipeline.output_url
        output_method = pipeline.output_method or "POST"

        success, response_data, error = await forwarder.forward(
            output_url, worker_payload, output_method
        )

        if success:
            status = "forwarded"
            response_code = 200
            if response_data:
                import json
                try:
                    response_body = json.dumps(response_data)
                except:
                    response_body = str(response_data)
            await save_job_status(job_id, str(pipeline.id), "forwarded")
            return WebhookReceivedResponse(
                success=True,
                job_id=job_id,
                message="Webhook received and forwarded successfully"
            )

        # Ensure job_id is present in worker_payload before queuing
        if "job_id" not in worker_payload:
            worker_payload["job_id"] = job_id

        # ── Worker is down — queue for retry ──
        status = "queued"
        error_msg = error
        if error and error.startswith("HTTP "):
            try:
                response_code = int(error.split(" ")[1].split(":")[0])
            except:
                pass
        await enqueue_for_retry(
            pipeline_id=str(pipeline.id),
            normalized=worker_payload,
            forward_url=output_url,
            forward_method=output_method,
        )
        await save_job_status(job_id, str(pipeline.id), "queued", last_error=error)

        return WebhookReceivedResponse(
            success=True,
            job_id=job_id,
            message=f"Worker unavailable — message queued for retry ({error})"
        )

    except HTTPException as he:
        if status == "pending":
            status = "error"
        if not error_msg:
            error_msg = str(he.detail)
        raise he
    except Exception as e:
        status = "error"
        error_msg = str(e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            duration = int((time.time() - start_time) * 1000)
            db_log = IngressLog(
                pipeline_id=pipeline_obj.id if pipeline_obj else None,
                pipeline_path=path,
                status=status,
                raw_payload=payload,
                output_payload=worker_payload,
                destination_url=dest_url or (pipeline_obj.output_url if pipeline_obj else None),
                response_code=response_code,
                response_body=response_body,
                duration_ms=duration,
                error_message=error_msg
            )
            db.add(db_log)
            await db.commit()
        except Exception as log_err:
            logger.error(f"Failed to save Ingress Log: {log_err}")


@router.post("/test/{path}", response_model=TestWebhookResponse)
async def test_webhook(
    path: str,
    test_request: TestWebhookRequest,
    db: AsyncSession = Depends(get_db)
):
    query = select(WebhookPipeline).where(
        WebhookPipeline.path == path,
        WebhookPipeline.is_active == True
    )
    result = await db.execute(query)
    pipeline = result.scalar_one_or_none()

    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found or inactive")

    try:
        normalized = normalize_webhook_payload(
            test_request.payload,
            pipeline.input_schema or {},
            path
        )
    except ValueError as e:
        logger.error(f"Validation error in test webhook payload for path '{path}': {e}. Payload: {test_request.payload}")
        raise HTTPException(status_code=400, detail=str(e))

    return TestWebhookResponse(
        success=True,
        pipeline=path,
        normalized=normalized,
        message="Test successful — payload normalized correctly"
    )


@router.get("/{path}")
async def get_pipeline_info(
    path: str,
    db: AsyncSession = Depends(get_db)
):
    query = select(WebhookPipeline).where(WebhookPipeline.path == path)
    result = await db.execute(query)
    pipeline = result.scalar_one_or_none()

    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    return {
        "id": str(pipeline.id),
        "name": pipeline.name,
        "path": pipeline.path,
        "is_active": pipeline.is_active,
        "auth_type": pipeline.auth_type,
        "input_schema": pipeline.input_schema,
        "output_url": pipeline.output_url,
    }