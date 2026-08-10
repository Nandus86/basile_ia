from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc, func, or_, cast, String
from typing import List, Optional
import uuid

from app.database import get_db
from app.models.user_analytics import UserAnalytics
from app.schemas.analytics import AnalyticsListResponse, UserAnalyticsResponse

router = APIRouter()

@router.get("/users", response_model=AnalyticsListResponse, summary="Listar Perfis Analíticos")
async def list_analytics(
    search: Optional[str] = None,
    church_id: Optional[str] = None,
    care_priority: Optional[str] = None,
    min_score: Optional[float] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=500),
    db: AsyncSession = Depends(get_db)
):
    """Retorna perfis analíticos, suportando filtros por igreja, prioridade, score e pesquisa textual."""
    query = select(UserAnalytics)
    
    if search:
        query = query.where(
            or_(
                UserAnalytics.session_id.ilike(f"%{search}%"),
                cast(UserAnalytics.profile_data, String).ilike(f"%{search}%")
            )
        )
        
    if church_id:
        query = query.where(UserAnalytics.church_id == church_id)
    if care_priority:
        query = query.where(UserAnalytics.care_priority == care_priority)
    if min_score is not None:
        query = query.where(UserAnalytics.engagement_score >= min_score)
        
    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()
    
    # Get rows
    query = query.order_by(desc(UserAnalytics.last_seen_at)).offset(skip).limit(limit)
    result = await db.execute(query)
    rows = result.scalars().all()
    
    return {
        "users": rows,
        "total": total,
        "skip": skip,
        "limit": limit
    }

@router.get("/users/{session_id}", response_model=UserAnalyticsResponse, summary="Obter Perfil Completo")
async def get_analytics(session_id: str, db: AsyncSession = Depends(get_db)):
    """Retorna o perfil JSONB completo e contadores para um session_id."""
    query = select(UserAnalytics).where(UserAnalytics.session_id == session_id)
    result = await db.execute(query)
    analytics = result.scalar_one_or_none()
    
    if not analytics:
        raise HTTPException(status_code=404, detail="Perfil analítico não encontrado para esta sessão.")
        
    return analytics

from app.models.analytics_config import AnalyticsConfig
from app.schemas.analytics import AnalyticsConfigResponse, AnalyticsConfigUpdate

@router.get("/config", response_model=AnalyticsConfigResponse, summary="Obter configuração do Agente Analista")
async def get_analytics_config(db: AsyncSession = Depends(get_db)):
    """Retorna as configurações atuais do Analista."""
    query = select(AnalyticsConfig).limit(1)
    result = await db.execute(query)
    config = result.scalar_one_or_none()
    
    if not config:
        config = AnalyticsConfig()
        db.add(config)
        await db.commit()
        await db.refresh(config)
        
    return config

@router.put("/config", response_model=AnalyticsConfigResponse, summary="Atualizar configuração do Agente Analista")
async def update_analytics_config(config_data: AnalyticsConfigUpdate, db: AsyncSession = Depends(get_db)):
    """Atualiza a configuração do Analista (Agente e Horário) e sincroniza o Scheduler."""
    query = select(AnalyticsConfig).limit(1)
    result = await db.execute(query)
    config = result.scalar_one_or_none()
    
    if not config:
        config = AnalyticsConfig()
        db.add(config)
        
    if config_data.agent_id is not None:
        config.agent_id = config_data.agent_id
    if config_data.church_agent_id is not None:
        config.church_agent_id = config_data.church_agent_id
    if config_data.system_agent_id is not None:
        config.system_agent_id = config_data.system_agent_id
    if config_data.cron_time is not None:
        config.cron_time = config_data.cron_time
    if config_data.church_report_time is not None:
        config.church_report_time = config_data.church_report_time
    if config_data.system_report_time is not None:
        config.system_report_time = config_data.system_report_time
    if config_data.user_webhook_url is not None:
        config.user_webhook_url = config_data.user_webhook_url
    if config_data.church_webhook_url is not None:
        config.church_webhook_url = config_data.church_webhook_url
    if config_data.system_webhook_url is not None:
        config.system_webhook_url = config_data.system_webhook_url
    if config_data.is_active is not None:
        config.is_active = config_data.is_active
    from sqlalchemy.orm.attributes import flag_modified
    if config_data.crm_mapping is not None:
        config.crm_mapping = config_data.crm_mapping
        flag_modified(config, "crm_mapping")
    if config_data.metrics_mapping is not None:
        config.metrics_mapping = config_data.metrics_mapping
        flag_modified(config, "metrics_mapping")
        
    await db.commit()
    await db.refresh(config)
    
    # Sync Scheduler immediately
    from app.services.analytics_scheduler import sync_analytics_scheduler
    await sync_analytics_scheduler()
    
    return config

@router.post("/users/{session_id}/run", summary="Forçar Análise Manual")
async def run_analytics_manual(session_id: str, db: AsyncSession = Depends(get_db)):
    """Coloca o usuário na fila do RabbitMQ para ser analisado imediatamente."""
    query = select(AnalyticsConfig).limit(1)
    result = await db.execute(query)
    config = result.scalar_one_or_none()
    
    if not config or not config.agent_id:
        raise HTTPException(status_code=400, detail="Nenhum agente analista configurado nas configurações de Analytics.")
        
    user_query = select(UserAnalytics).where(UserAnalytics.session_id == session_id)
    user_res = await db.execute(user_query)
    user = user_res.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        
    from app.services.rabbitmq_service import rabbitmq_client
    await rabbitmq_client.connect()
    
    payload = {
        "session_id": session_id,
        "agent_id": str(config.agent_id)
    }
    
    try:
        await rabbitmq_client.publish_message(
            exchange_name="",
            routing_key="analytics_tasks",
            message_body=payload
        )
        return {"status": "queued", "message": "Análise enviada para a fila de processamento."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao enfileirar tarefa: {str(e)}")

@router.post("/users/run-all", summary="Forçar Análise de Todos os Usuários")
async def run_all_analytics_manual(target_date: str = Body(..., embed=True), db: AsyncSession = Depends(get_db)):
    """
    Busca todos os usuários com interaction_count >= 3 e os coloca na fila
    para análise manual forçada (útil para retroativos).
    A 'target_date' aqui serve apenas como referência para log,
    ou para usar futuramente na lógica de filtragem se necessário.
    """
    query = select(AnalyticsConfig).limit(1)
    result = await db.execute(query)
    config = result.scalar_one_or_none()
    
    if not config or not config.agent_id:
        raise HTTPException(status_code=400, detail="Nenhum agente analista configurado nas configurações de Analytics.")
        
    user_query = select(UserAnalytics).where(UserAnalytics.interaction_count >= 3)
    user_res = await db.execute(user_query)
    users = user_res.scalars().all()
    
    if not users:
        return {"status": "success", "message": "Nenhum usuário elegível encontrado para análise.", "queued": 0}
        
    from app.services.rabbitmq_service import rabbitmq_client
    await rabbitmq_client.connect()
    
    queued = 0
    for user in users:
        payload = {
            "session_id": user.session_id,
            "agent_id": str(config.agent_id),
            "target_date": target_date
        }
        try:
            await rabbitmq_client.publish_message(
                exchange_name="",
                routing_key="analytics_tasks",
                message_body=payload
            )
            queued += 1
        except Exception as e:
            print(f"Error queueing user {user.session_id}: {e}")
            
    return {"status": "success", "message": f"{queued} usuários enviados para a fila de processamento.", "queued": queued}

from app.models.analytics_report import AnalyticsReport
from app.schemas.analytics import AnalyticsReportListResponse, AnalyticsReportResponse
from datetime import datetime

@router.get("/reports", response_model=AnalyticsReportListResponse, summary="Listar Relatórios")
async def list_reports(
    level: str = Query(..., description="user, church, ou system"),
    period_type: str = Query(..., description="daily, weekly, ou monthly"),
    entity_id: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=100),
    db: AsyncSession = Depends(get_db)
):
    query = select(AnalyticsReport).where(
        AnalyticsReport.level == level,
        AnalyticsReport.period_type == period_type
    )
    
    if entity_id:
        query = query.where(AnalyticsReport.entity_id == entity_id)
    if date_from:
        query = query.where(AnalyticsReport.period_start >= date_from)
    if date_to:
        query = query.where(AnalyticsReport.period_start <= date_to)
        
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()
    
    query = query.order_by(desc(AnalyticsReport.period_start)).offset(skip).limit(limit)
    rows = (await db.execute(query)).scalars().all()
    
    return {"reports": rows, "total": total, "skip": skip, "limit": limit}

@router.get("/reports/{report_id}", response_model=AnalyticsReportResponse, summary="Detalhes do Relatório")
async def get_report(report_id: str, db: AsyncSession = Depends(get_db)):
    query = select(AnalyticsReport).where(AnalyticsReport.id == report_id)
    report = (await db.execute(query)).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")
    return report

from pydantic import BaseModel
class GenerateReportRequest(BaseModel):
    level: str
    period_type: str
    entity_id: str
    entity_name: str
    start_time: datetime
    end_time: datetime

@router.post("/reports/generate", summary="Gerar Relatório Manual")
async def generate_report_manual(req: GenerateReportRequest, db: AsyncSession = Depends(get_db)):
    from app.services.analytics_scheduler import queue_report_task
    await queue_report_task(req.level, req.period_type, req.entity_id, req.entity_name, req.start_time, req.end_time)
    return {"status": "queued", "message": "Geração do relatório iniciada."}

@router.get("/churches", summary="Listar Igrejas para Filtro")
async def list_churches(db: AsyncSession = Depends(get_db)):
    """Busca IDs distintos de igrejas e resolve seus nomes reais."""
    query = select(UserAnalytics.church_id).where(UserAnalytics.church_id != None).distinct()
    church_ids = (await db.execute(query)).scalars().all()
    
    results = []
    for cid in church_ids:
        if not cid:
            continue
        # Tenta resolver o nome a partir da zona CRM de qualquer usuário dessa igreja
        user_res = await db.execute(
            select(UserAnalytics.profile_data).where(UserAnalytics.church_id == cid).limit(1)
        )
        profile = user_res.scalar_one_or_none()
        name = None
        if profile and isinstance(profile, dict):
            crm = profile.get("__zona_crm", {})
            name = crm.get("church_name") or crm.get("Igreja Sede")
        
        # Fallback: tenta no job_logs
        if not name:
            from app.models.job_log import JobLog
            log_res = await db.execute(
                select(JobLog.church_name).where(JobLog.church_name != None, JobLog.church_name != "").limit(1)
            )
            name = log_res.scalar_one_or_none()
        
        results.append({"id": cid, "name": name or cid})
    
    return results
