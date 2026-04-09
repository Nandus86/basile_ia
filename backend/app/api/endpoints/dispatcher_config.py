from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.future import select
from typing import List
from uuid import UUID

from app.database import get_db
from app.models.dispatcher_config import DispatcherConfig
from app.schemas.dispatcher_config import DispatcherConfigCreate, DispatcherConfigUpdate, DispatcherConfigResponse, DispatcherConfigList

router = APIRouter()

@router.get("", response_model=DispatcherConfigList)
@router.get("/", response_model=DispatcherConfigList, include_in_schema=False)
async def list_dispatcher_configs(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    """List all Dispatcher Configs."""
    query = select(DispatcherConfig).offset(skip).limit(limit)
    result = await db.execute(query)
    configs = result.scalars().all()
    
    count_query = select(DispatcherConfig.id)
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())
    
    resp_configs = []
    for c in configs:
        agent_name = c.agent.name if c.agent else None
        resp_configs.append(DispatcherConfigResponse(
            id=c.id,
            name=c.name,
            path=c.path,
            buttons_enabled=c.buttons_enabled,
            buttons=c.buttons,
            image_enabled=c.image_enabled,
            messages_per_batch=c.messages_per_batch,
            agent_id=c.agent_id,
            start_time=c.start_time,
            end_time=c.end_time,
            start_delay_seconds=c.start_delay_seconds,
            min_variation_seconds=c.min_variation_seconds,
            max_variation_seconds=c.max_variation_seconds,
            triggers=c.triggers,
            index_max=c.index_max,
            progress_callback_url=c.progress_callback_url,
            is_active=c.is_active,
            has_api_key=bool(c.api_key),
            agent_name=agent_name,
            created_at=c.created_at,
            updated_at=c.updated_at
        ))
    
    return DispatcherConfigList(configs=resp_configs, total=total)

@router.post("", response_model=DispatcherConfigResponse)
@router.post("/", response_model=DispatcherConfigResponse, include_in_schema=False)
async def create_dispatcher_config(config: DispatcherConfigCreate, db: Session = Depends(get_db)):
    """Create a new Dispatcher Config."""
    query = select(DispatcherConfig).where(DispatcherConfig.path == config.path)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Dispatcher config with this path already exists")
        
    db_config = DispatcherConfig(
        name=config.name,
        path=config.path,
        api_key=config.api_key,
        buttons_enabled=config.buttons_enabled,
        buttons=[b.dict() for b in config.buttons],
        image_enabled=config.image_enabled,
        messages_per_batch=config.messages_per_batch,
        agent_id=config.agent_id,
        start_time=config.start_time,
        end_time=config.end_time,
        start_delay_seconds=config.start_delay_seconds,
        min_variation_seconds=config.min_variation_seconds,
        max_variation_seconds=config.max_variation_seconds,
        triggers=config.triggers,
        index_max=config.index_max,
        progress_callback_url=config.progress_callback_url,
        is_active=config.is_active
    )
    db.add(db_config)
    await db.commit()
    await db.refresh(db_config)
    
    agent_name = db_config.agent.name if db_config.agent else None
    
    return DispatcherConfigResponse(
        id=db_config.id,
        name=db_config.name,
        path=db_config.path,
        buttons_enabled=db_config.buttons_enabled,
        buttons=db_config.buttons,
        image_enabled=db_config.image_enabled,
        messages_per_batch=db_config.messages_per_batch,
        agent_id=db_config.agent_id,
        start_time=db_config.start_time,
        end_time=db_config.end_time,
        start_delay_seconds=db_config.start_delay_seconds,
        min_variation_seconds=db_config.min_variation_seconds,
        max_variation_seconds=db_config.max_variation_seconds,
        triggers=db_config.triggers,
        index_max=db_config.index_max,
        progress_callback_url=db_config.progress_callback_url,
        is_active=db_config.is_active,
        has_api_key=bool(db_config.api_key),
        agent_name=agent_name,
        created_at=db_config.created_at,
        updated_at=db_config.updated_at
    )

@router.get("/by-path/{path}", response_model=DispatcherConfigResponse)
async def get_dispatcher_config_by_path(path: str, db: Session = Depends(get_db)):
    """Get a specific Dispatcher Config by path."""
    query = select(DispatcherConfig).where(DispatcherConfig.path == path)
    result = await db.execute(query)
    c = result.scalar_one_or_none()
    
    if not c:
        raise HTTPException(status_code=404, detail="Dispatcher config not found")
        
    agent_name = c.agent.name if c.agent else None
        
    return DispatcherConfigResponse(
        id=c.id,
        name=c.name,
        path=c.path,
        buttons_enabled=c.buttons_enabled,
        buttons=c.buttons,
        image_enabled=c.image_enabled,
        messages_per_batch=c.messages_per_batch,
        agent_id=c.agent_id,
        start_time=c.start_time,
        end_time=c.end_time,
        start_delay_seconds=c.start_delay_seconds,
        min_variation_seconds=c.min_variation_seconds,
        max_variation_seconds=c.max_variation_seconds,
        triggers=c.triggers,
        index_max=c.index_max,
        progress_callback_url=c.progress_callback_url,
        is_active=c.is_active,
        has_api_key=bool(c.api_key),
        agent_name=agent_name,
        created_at=c.created_at,
        updated_at=c.updated_at
    )

@router.get("/{config_id}", response_model=DispatcherConfigResponse)
async def get_dispatcher_config(config_id: UUID, db: Session = Depends(get_db)):
    """Get a specific Dispatcher Config by ID."""
    query = select(DispatcherConfig).where(DispatcherConfig.id == config_id)
    result = await db.execute(query)
    c = result.scalar_one_or_none()
    
    if not c:
        raise HTTPException(status_code=404, detail="Dispatcher config not found")
        
    agent_name = c.agent.name if c.agent else None
        
    return DispatcherConfigResponse(
        id=c.id,
        name=c.name,
        path=c.path,
        buttons_enabled=c.buttons_enabled,
        buttons=c.buttons,
        image_enabled=c.image_enabled,
        messages_per_batch=c.messages_per_batch,
        agent_id=c.agent_id,
        start_time=c.start_time,
        end_time=c.end_time,
        start_delay_seconds=c.start_delay_seconds,
        min_variation_seconds=c.min_variation_seconds,
        max_variation_seconds=c.max_variation_seconds,
        triggers=c.triggers,
        index_max=c.index_max,
        progress_callback_url=c.progress_callback_url,
        is_active=c.is_active,
        has_api_key=bool(c.api_key),
        agent_name=agent_name,
        created_at=c.created_at,
        updated_at=c.updated_at
    )

@router.put("/{config_id}", response_model=DispatcherConfigResponse)
async def update_dispatcher_config(config_id: UUID, config_update: DispatcherConfigUpdate, db: Session = Depends(get_db)):
    """Update a Dispatcher Config."""
    query = select(DispatcherConfig).where(DispatcherConfig.id == config_id)
    result = await db.execute(query)
    db_config = result.scalar_one_or_none()
    
    if not db_config:
        raise HTTPException(status_code=404, detail="Dispatcher config not found")
        
    if config_update.path is not None and config_update.path != db_config.path:
        path_check = await db.execute(select(DispatcherConfig).where(DispatcherConfig.path == config_update.path))
        if path_check.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Dispatcher config with this path already exists")
            
    update_data = config_update.dict(exclude_unset=True)
    if "buttons" in update_data and update_data["buttons"] is not None:
        update_data["buttons"] = [b.dict() if hasattr(b, 'dict') else b for b in update_data["buttons"]]
        
    for key, value in update_data.items():
        setattr(db_config, key, value)
        
    await db.commit()
    await db.refresh(db_config)
    
    agent_name = db_config.agent.name if db_config.agent else None
    
    return DispatcherConfigResponse(
        id=db_config.id,
        name=db_config.name,
        path=db_config.path,
        buttons_enabled=db_config.buttons_enabled,
        buttons=db_config.buttons,
        image_enabled=db_config.image_enabled,
        messages_per_batch=db_config.messages_per_batch,
        agent_id=db_config.agent_id,
        start_time=db_config.start_time,
        end_time=db_config.end_time,
        start_delay_seconds=db_config.start_delay_seconds,
        min_variation_seconds=db_config.min_variation_seconds,
        max_variation_seconds=db_config.max_variation_seconds,
        triggers=db_config.triggers,
        index_max=db_config.index_max,
        progress_callback_url=db_config.progress_callback_url,
        is_active=db_config.is_active,
        has_api_key=bool(db_config.api_key),
        agent_name=agent_name,
        created_at=db_config.created_at,
        updated_at=db_config.updated_at
    )

@router.delete("/{config_id}")
async def delete_dispatcher_config(config_id: UUID, db: Session = Depends(get_db)):
    """Delete a Dispatcher Config."""
    query = select(DispatcherConfig).where(DispatcherConfig.id == config_id)
    result = await db.execute(query)
    c = result.scalar_one_or_none()
    
    if not c:
        raise HTTPException(status_code=404, detail="Dispatcher config not found")
        
    await db.delete(c)
    await db.commit()
    return {"message": "Dispatcher config deleted successfully"}
