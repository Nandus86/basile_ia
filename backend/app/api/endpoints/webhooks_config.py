from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.future import select
from typing import List
from uuid import UUID

from app.database import get_db
from app.models.webhook_config import WebhookConfig
from app.schemas.webhook_config import WebhookConfigCreate, WebhookConfigUpdate, WebhookConfigResponse, WebhookConfigList

router = APIRouter()

@router.get("", response_model=WebhookConfigList)
@router.get("/", response_model=WebhookConfigList, include_in_schema=False)
async def list_webhook_configs(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    """List all Webhook Configs."""
    query = select(WebhookConfig).offset(skip).limit(limit)
    result = await db.execute(query)
    configs = result.scalars().all()
    
    count_query = select(WebhookConfig.id)
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())
    
    resp_configs = []
    for c in configs:
        resp_configs.append(WebhookConfigResponse(
            id=c.id,
            name=c.name,
            path=c.path,
            require_token=c.require_token,
            target_agent_id=c.target_agent_id,
            is_active=c.is_active,
            has_token=bool(c.access_token),
            created_at=c.created_at,
            updated_at=c.updated_at
        ))
    
    return WebhookConfigList(webhooks=resp_configs, total=total)

@router.post("", response_model=WebhookConfigResponse)
@router.post("/", response_model=WebhookConfigResponse, include_in_schema=False)
async def create_webhook_config(config: WebhookConfigCreate, db: Session = Depends(get_db)):
    """Create a new Webhook Config."""
    # Check if path already exists
    query = select(WebhookConfig).where(WebhookConfig.path == config.path)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Webhook with this path already exists")
        
    if config.require_token and not config.access_token:
        raise HTTPException(status_code=400, detail="access_token is required when require_token is true")
        
    db_config = WebhookConfig(
        name=config.name,
        path=config.path,
        require_token=config.require_token,
        access_token=config.access_token,
        target_agent_id=config.target_agent_id,
        is_active=config.is_active
    )
    db.add(db_config)
    await db.commit()
    await db.refresh(db_config)
    
    return WebhookConfigResponse(
        id=db_config.id,
        name=db_config.name,
        path=db_config.path,
        require_token=db_config.require_token,
        target_agent_id=db_config.target_agent_id,
        is_active=db_config.is_active,
        has_token=bool(db_config.access_token),
        created_at=db_config.created_at,
        updated_at=db_config.updated_at
    )

@router.get("/{config_id}", response_model=WebhookConfigResponse)
async def get_webhook_config(config_id: UUID, db: Session = Depends(get_db)):
    """Get a specific Webhook Config by ID."""
    query = select(WebhookConfig).where(WebhookConfig.id == config_id)
    result = await db.execute(query)
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(status_code=404, detail="Webhook config not found")
        
    return WebhookConfigResponse(
        id=config.id,
        name=config.name,
        path=config.path,
        require_token=config.require_token,
        target_agent_id=config.target_agent_id,
        is_active=config.is_active,
        has_token=bool(config.access_token),
        created_at=config.created_at,
        updated_at=config.updated_at
    )

@router.put("/{config_id}", response_model=WebhookConfigResponse)
async def update_webhook_config(config_id: UUID, config_update: WebhookConfigUpdate, db: Session = Depends(get_db)):
    """Update a Webhook Config."""
    query = select(WebhookConfig).where(WebhookConfig.id == config_id)
    result = await db.execute(query)
    db_config = result.scalar_one_or_none()
    
    if not db_config:
        raise HTTPException(status_code=404, detail="Webhook config not found")
        
    # Check path uniqueness if path is being updated
    if config_update.path is not None and config_update.path != db_config.path:
        path_check = await db.execute(select(WebhookConfig).where(WebhookConfig.path == config_update.path))
        if path_check.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Webhook with this path already exists")
            
    update_data = config_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_config, key, value)
        
    await db.commit()
    await db.refresh(db_config)
    
    return WebhookConfigResponse(
        id=db_config.id,
        name=db_config.name,
        path=db_config.path,
        require_token=db_config.require_token,
        target_agent_id=db_config.target_agent_id,
        is_active=db_config.is_active,
        has_token=bool(db_config.access_token),
        created_at=db_config.created_at,
        updated_at=db_config.updated_at
    )

@router.delete("/{config_id}")
async def delete_webhook_config(config_id: UUID, db: Session = Depends(get_db)):
    """Delete a Webhook Config."""
    query = select(WebhookConfig).where(WebhookConfig.id == config_id)
    result = await db.execute(query)
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(status_code=404, detail="Webhook config not found")
        
    await db.delete(config)
    await db.commit()
    return {"message": "Webhook config deleted successfully"}
