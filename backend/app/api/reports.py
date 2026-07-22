"""
Admin System & Church Reporting Endpoints
Provides read-only GET endpoints for System Administration and Church-level attendance reports.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, or_, and_
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import json
import re

from app.database import get_db, AsyncSessionLocal
from app.models.job_log import JobLog
from app.models.conversation_message import ConversationMessage
from app.models.agent import Agent
from app.redis_client import redis_client

admin_router = APIRouter(prefix="/admin/system", tags=["Admin - Sistema"])
church_router = APIRouter(prefix="/reports/church", tags=["Relatórios - Igreja"])


# ─────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────

from sqlalchemy import cast, String

def _build_church_filter(identifier: str):
    """
    Build SQLAlchemy filter condition to match a church by:
    - church_name (string column)
    - global.instancia (JSON extract)
    - church._id (JSON extract)
    - member.church_id (JSON extract)
    """
    cleaned_id = identifier.strip()
    return or_(
        JobLog.church_name.ilike(f"%{cleaned_id}%"),
        func.json_extract_path_text(JobLog.request_data, "global", "instancia") == cleaned_id,
        func.json_extract_path_text(JobLog.request_data, "church", "_id") == cleaned_id,
        func.json_extract_path_text(JobLog.request_data, "member", "church_id") == cleaned_id,
        cast(JobLog.request_data["global"]["instancia"], String).ilike(f"%{cleaned_id}%"),
        cast(JobLog.request_data["church"]["_id"], String).ilike(f"%{cleaned_id}%"),
        cast(JobLog.request_data["member"]["church_id"], String).ilike(f"%{cleaned_id}%"),
    )


# ─────────────────────────────────────────────────────────────
# GROUP 1: ADMIN - SISTEMA
# ─────────────────────────────────────────────────────────────

@admin_router.get("/health", summary="Visão geral de saúde do sistema e infraestrutura")
async def get_system_health(db: AsyncSession = Depends(get_db)):
    """
    Retorna o status de saúde operacional da infraestrutura (PostgreSQL, Redis, Uptime).
    """
    db_status = "healthy"
    try:
        await db.execute(select(1))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    redis_status = "healthy"
    try:
        if hasattr(redis_client, "ping"):
            await redis_client.ping()
        elif hasattr(redis_client, "redis") and redis_client.redis:
            await redis_client.redis.ping()
    except Exception as e:
        redis_status = f"unhealthy: {str(e)}"

    return {
        "status": "online" if db_status == "healthy" and redis_status == "healthy" else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": {
            "database_postgresql": db_status,
            "redis_cache": redis_status,
        }
    }


@admin_router.get("/metrics", summary="Métricas globais do sistema e desempenho")
async def get_system_metrics(db: AsyncSession = Depends(get_db)):
    """
    Retorna estatísticas agregadas de atendimentos: total de jobs, taxa de erro (%), 
    tempo médio de processamento (ms) e total de mensagens no MTM.
    """
    # Job stats
    total_jobs_q = await db.execute(select(func.count(JobLog.id)))
    total_jobs = total_jobs_q.scalar_one() or 0

    completed_q = await db.execute(select(func.count(JobLog.id)).where(JobLog.status == "completed"))
    completed_jobs = completed_q.scalar_one() or 0

    failed_q = await db.execute(select(func.count(JobLog.id)).where(JobLog.status == "failed"))
    failed_jobs = failed_q.scalar_one() or 0

    avg_dur_q = await db.execute(select(func.avg(JobLog.duration_ms)).where(JobLog.status == "completed"))
    avg_duration_ms = avg_dur_q.scalar_one() or 0.0

    # Total MTM messages
    msg_q = await db.execute(select(func.count(ConversationMessage.id)))
    total_messages = msg_q.scalar_one() or 0

    # Distinct active churches count
    churches_q = await db.execute(select(func.count(func.distinct(JobLog.church_name))))
    total_churches = churches_q.scalar_one() or 0

    error_rate_pct = round((failed_jobs / total_jobs * 100), 2) if total_jobs > 0 else 0.0

    return {
        "total_jobs": total_jobs,
        "completed_jobs": completed_jobs,
        "failed_jobs": failed_jobs,
        "error_rate_pct": error_rate_pct,
        "avg_duration_ms": round(float(avg_duration_ms), 2),
        "total_messages": total_messages,
        "total_active_churches": total_churches,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@admin_router.get("/jobs", summary="Histórico técnico de jobs e execuções de webhook")
async def list_system_jobs(
    status: Optional[str] = Query(None, description="Filtra por status: completed, failed, queued, in_progress"),
    church_name: Optional[str] = Query(None, description="Filtra pelo nome da igreja"),
    instancia: Optional[str] = Query(None, description="Filtra pelo ID da instância (global.instancia)"),
    limit: int = Query(50, le=500),
    skip: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """
    Lista todos os jobs com suporte a filtros técnicos (status, igreja, instância).
    """
    q = select(JobLog)

    if status:
        q = q.where(JobLog.status == status)

    if church_name:
        q = q.where(JobLog.church_name.ilike(f"%{church_name}%"))

    if instancia:
        q = q.where(
            or_(
                func.json_extract_path_text(JobLog.request_data, "global", "instancia") == instancia,
                cast(JobLog.request_data["global"]["instancia"], String).ilike(f"%{instancia}%")
            )
        )

    # Count total matching
    count_q = select(func.count()).select_from(q.subquery())
    total_res = await db.execute(count_q)
    total = total_res.scalar_one() or 0

    # Fetch rows
    q = q.order_by(desc(JobLog.created_at)).offset(skip).limit(limit)
    res = await db.execute(q)
    rows = res.scalars().all()

    items = []
    for log in rows:
        req = log.request_data or {}
        glob = req.get("global") or {}
        items.append({
            "id": str(log.id),
            "job_id": log.job_id,
            "webhook_path": log.webhook_path,
            "status": log.status,
            "church_name": log.church_name,
            "instancia": glob.get("instancia"),
            "member_name": log.member_name,
            "user_message": log.user_message,
            "agent_response": log.agent_response,
            "duration_ms": log.duration_ms,
            "error_message": log.error_message,
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "completed_at": log.completed_at.isoformat() if log.completed_at else None,
        })

    return {"items": items, "count": len(items), "total": total, "limit": limit, "skip": skip}


@admin_router.get("/churches", summary="Lista de igrejas ativas e estatísticas globais")
async def list_active_churches(db: AsyncSession = Depends(get_db)):
    """
    Retorna a lista de todas as igrejas ativas identificadas no sistema com estatísticas agregadas.
    """
    q = (
        select(
            JobLog.church_name,
            func.count(JobLog.id).label("total_attendances"),
            func.max(JobLog.created_at).label("last_activity"),
            func.min(JobLog.created_at).label("first_activity"),
        )
        .where(JobLog.church_name.isnot(None))
        .group_by(JobLog.church_name)
        .order_by(desc(func.max(JobLog.created_at)))
    )

    res = await db.execute(q)
    rows = res.all()

    churches = []
    for r in rows:
        churches.append({
            "church_name": r.church_name,
            "total_attendances": r.total_attendances,
            "last_activity": r.last_activity.isoformat() if r.last_activity else None,
            "first_activity": r.first_activity.isoformat() if r.first_activity else None,
        })

    return {"churches": churches, "total_churches": len(churches)}


# ─────────────────────────────────────────────────────────────
# GROUP 2: RELATÓRIOS - IGREJA
# ─────────────────────────────────────────────────────────────

@church_router.get("/{church_identifier}/summary", summary="Resumo executivo de atendimentos da igreja")
async def get_church_summary(
    church_identifier: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Retorna estatísticas consolidadas para o pastor: total de membros atendidos, 
    total de interações e última atividade. O church_identifier aceita global.instancia, 
    church._id ou o nome da igreja.
    """
    condition = _build_church_filter(church_identifier)

    # Total attendances
    total_q = await db.execute(select(func.count(JobLog.id)).where(condition))
    total_attendances = total_q.scalar_one() or 0

    if total_attendances == 0:
        return {
            "church_identifier": church_identifier,
            "found": False,
            "message": f"Nenhum registro encontrado para a igreja '{church_identifier}'."
        }

    # Unique members
    members_q = await db.execute(select(func.count(func.distinct(JobLog.member_name))).where(condition))
    unique_members = members_q.scalar_one() or 0

    # Completed vs Failed
    comp_q = await db.execute(select(func.count(JobLog.id)).where(and_(condition, JobLog.status == "completed")))
    completed = comp_q.scalar_one() or 0

    # Last active timestamp & Church name
    info_q = await db.execute(
        select(JobLog.church_name, func.max(JobLog.created_at))
        .where(condition)
        .group_by(JobLog.church_name)
    )
    info_row = info_q.first()
    resolved_church_name = info_row[0] if info_row else church_identifier
    last_active = info_row[1].isoformat() if info_row and info_row[1] else None

    return {
        "church_identifier": church_identifier,
        "resolved_church_name": resolved_church_name,
        "found": True,
        "metrics": {
            "total_attendances": total_attendances,
            "unique_members_attended": unique_members,
            "successful_attendances": completed,
            "last_attendance_at": last_active,
        }
    }


@church_router.get("/{church_identifier}/attendances", summary="Lista de atendimentos dos membros da igreja")
async def list_church_attendances(
    church_identifier: str,
    limit: int = Query(50, le=500),
    skip: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """
    Retorna a lista de atendimentos realizados para os fiéis/visitantes da igreja, 
    sem jargões técnicos dos agentes.
    """
    condition = _build_church_filter(church_identifier)

    # Count total
    count_q = select(func.count(JobLog.id)).where(condition)
    total_res = await db.execute(count_q)
    total = total_res.scalar_one() or 0

    # Fetch attendances
    q = (
        select(JobLog)
        .where(condition)
        .order_by(desc(JobLog.created_at))
        .offset(skip)
        .limit(limit)
    )
    res = await db.execute(q)
    rows = res.scalars().all()

    attendances = []
    for log in rows:
        req = log.request_data or {}
        glob = req.get("global") or {}
        memb = req.get("member") or {}
        memb_fin = req.get("member_fin") or {}

        phone = (
            glob.get("phone")
            or glob.get("user_phone")
            or memb.get("phone")
            or memb_fin.get("phone")
            or ""
        )

        role = memb_fin.get("role_profile") or memb.get("role") or "Membro"

        attendances.append({
            "session_id": log.session_id,
            "job_id": log.job_id,
            "member_name": log.member_name or "Visitante / Anônimo",
            "member_phone": phone,
            "member_role": role,
            "user_message": log.user_message,
            "agent_response": log.agent_response,
            "status": "Concluído" if log.status == "completed" else log.status,
            "duration_seconds": round((log.duration_ms or 0) / 1000.0, 1),
            "created_at": log.created_at.isoformat() if log.created_at else None,
        })

    return {
        "church_identifier": church_identifier,
        "attendances": attendances,
        "count": len(attendances),
        "total": total,
        "limit": limit,
        "skip": skip
    }


@church_router.get("/{church_identifier}/attendances/{session_id}", summary="Detalhes completos de 1 atendimento (Payload In/Out + MTM)")
async def get_attendance_details(
    church_identifier: str,
    session_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Retorna o histórico completo do atendimento de um membro: payload de entrada, 
    resposta gerada e todas as mensagens MTM da conversa.
    """
    condition = and_(_build_church_filter(church_identifier), JobLog.session_id == session_id)

    # Fetch job log
    job_q = await db.execute(select(JobLog).where(condition).order_by(desc(JobLog.created_at)).limit(1))
    log = job_q.scalar_one_or_none()

    req_data = log.request_data if log else {}
    resp_data = log.response_data if log else {}

    # Fetch MTM conversation messages for this session
    mtm_q = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.session_id == session_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    mtm_rows = mtm_q.scalars().all()

    mtm_messages = []
    for msg in mtm_rows:
        mtm_messages.append({
            "role": msg.role,
            "content": msg.content,
            "timestamp": msg.created_at.isoformat() if msg.created_at else None,
        })

    # Extract member and church info
    glob = req_data.get("global") or {}
    church_data = req_data.get("church") or {}
    memb = req_data.get("member") or {}
    memb_fin = req_data.get("member_fin") or {}

    return {
        "session_id": session_id,
        "church": {
            "name": church_data.get("church_name") or (log.church_name if log else None),
            "instancia": glob.get("instancia"),
            "id": church_data.get("_id"),
        },
        "member": {
            "name": log.member_name if log else (memb.get("fullname") or glob.get("name")),
            "phone": glob.get("phone") or memb.get("phone"),
            "role_profile": memb_fin.get("role_profile") or memb.get("role"),
        },
        "initial_user_message": log.user_message if log else None,
        "final_agent_response": log.agent_response if log else None,
        "full_input_payload": req_data,
        "full_output_payload": resp_data,
        "mtm_conversation_history": mtm_messages,
        "created_at": log.created_at.isoformat() if log and log.created_at else None,
    }


@church_router.get("/{church_identifier}/prayer-requests", summary="Pedidos de oração e intenções recebidas")
async def list_prayer_requests(
    church_identifier: str,
    limit: int = Query(50, le=500),
    skip: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """
    Filtra atendimentos da igreja onde o membro enviou um pedido de oração ou intenção espiritual.
    """
    base_condition = _build_church_filter(church_identifier)

    # Keywords matching prayer requests
    prayer_keywords = ["oração", "oracao", "orar", "interceder", "intercessão", "clamor", "benção", "bencao", "cura", "libertação", "libertacao"]
    prayer_conditions = [JobLog.user_message.ilike(f"%{kw}%") for kw in prayer_keywords]

    condition = and_(base_condition, or_(*prayer_conditions))

    # Count matching
    count_q = select(func.count(JobLog.id)).where(condition)
    total_res = await db.execute(count_q)
    total = total_res.scalar_one() or 0

    # Fetch rows
    q = select(JobLog).where(condition).order_by(desc(JobLog.created_at)).offset(skip).limit(limit)
    res = await db.execute(q)
    rows = res.scalars().all()

    requests = []
    for log in rows:
        req = log.request_data or {}
        glob = req.get("global") or {}
        memb = req.get("member") or {}
        phone = glob.get("phone") or memb.get("phone") or ""

        requests.append({
            "session_id": log.session_id,
            "member_name": log.member_name or "Membro",
            "member_phone": phone,
            "prayer_request": log.user_message,
            "agent_response": log.agent_response,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        })

    return {
        "church_identifier": church_identifier,
        "prayer_requests": requests,
        "count": len(requests),
        "total": total,
        "limit": limit,
        "skip": skip
    }
