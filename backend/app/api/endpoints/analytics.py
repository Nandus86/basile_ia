from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc, func
from typing import List, Optional
import uuid

from app.database import get_db
from app.models.user_analytics import UserAnalytics
from app.schemas.analytics import AnalyticsListResponse, UserAnalyticsResponse

router = APIRouter()

@router.get("/users", response_model=AnalyticsListResponse, summary="Listar Perfis Analíticos")
async def list_analytics(
    church_id: Optional[str] = None,
    care_priority: Optional[str] = None,
    min_score: Optional[float] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=500),
    db: AsyncSession = Depends(get_db)
):
    """Retorna perfis analíticos, suportando filtros por igreja, prioridade e score (consumido pelo CRM)."""
    query = select(UserAnalytics)
    
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
    if config_data.cron_time is not None:
        config.cron_time = config_data.cron_time
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
