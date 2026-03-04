from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.future import select
from typing import List
from uuid import UUID

from app.database import get_db
from app.models.ai_provider import AIProvider
from app.schemas.ai_provider import AIProviderCreate, AIProviderUpdate, AIProviderResponse, AIProviderList

router = APIRouter()

@router.get("", response_model=AIProviderList)
@router.get("/", response_model=AIProviderList, include_in_schema=False)
async def list_providers(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    """List all AI Providers."""
    query = select(AIProvider).offset(skip).limit(limit)
    result = await db.execute(query)
    providers = result.scalars().all()
    
    count_query = select(AIProvider.id)
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())
    
    # Map to schema formatting
    resp_providers = []
    for p in providers:
        resp_providers.append(AIProviderResponse(
            id=p.id,
            name=p.name,
            base_url=p.base_url,
            default_model=p.default_model,
            is_active=p.is_active,
            api_key_configured=bool(p.api_key),
            created_at=p.created_at,
            updated_at=p.updated_at
        ))
    
    return AIProviderList(providers=resp_providers, total=total)

@router.post("", response_model=AIProviderResponse)
@router.post("/", response_model=AIProviderResponse, include_in_schema=False)
async def create_provider(provider: AIProviderCreate, db: Session = Depends(get_db)):
    """Create a new AI Provider configuration."""
    # Check if name already exists
    query = select(AIProvider).where(AIProvider.name == provider.name)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Provider with this name already exists")
        
    db_provider = AIProvider(
        name=provider.name,
        base_url=provider.base_url,
        api_key=provider.api_key,
        default_model=provider.default_model,
        is_active=provider.is_active
    )
    db.add(db_provider)
    await db.commit()
    await db.refresh(db_provider)
    
    return AIProviderResponse(
        id=db_provider.id,
        name=db_provider.name,
        base_url=db_provider.base_url,
        default_model=db_provider.default_model,
        is_active=db_provider.is_active,
        api_key_configured=bool(db_provider.api_key),
        created_at=db_provider.created_at,
        updated_at=db_provider.updated_at
    )

@router.get("/{provider_id}", response_model=AIProviderResponse)
async def get_provider(provider_id: UUID, db: Session = Depends(get_db)):
    """Get a specific AI Provider configuration."""
    query = select(AIProvider).where(AIProvider.id == provider_id)
    result = await db.execute(query)
    provider = result.scalar_one_or_none()
    
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
        
    return AIProviderResponse(
        id=provider.id,
        name=provider.name,
        base_url=provider.base_url,
        default_model=provider.default_model,
        is_active=provider.is_active,
        api_key_configured=bool(provider.api_key),
        created_at=provider.created_at,
        updated_at=provider.updated_at
    )

@router.put("/{provider_id}", response_model=AIProviderResponse)
async def update_provider(provider_id: UUID, provider_update: AIProviderUpdate, db: Session = Depends(get_db)):
    """Update an AI Provider configuration."""
    query = select(AIProvider).where(AIProvider.id == provider_id)
    result = await db.execute(query)
    db_provider = result.scalar_one_or_none()
    
    if not db_provider:
        raise HTTPException(status_code=404, detail="Provider not found")
        
    # Check name uniqueness if name is being updated
    if provider_update.name is not None and provider_update.name != db_provider.name:
        name_check = await db.execute(select(AIProvider).where(AIProvider.name == provider_update.name))
        if name_check.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Provider with this name already exists")
            
    update_data = provider_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_provider, key, value)
        
    await db.commit()
    await db.refresh(db_provider)
    
    return AIProviderResponse(
        id=db_provider.id,
        name=db_provider.name,
        base_url=db_provider.base_url,
        default_model=db_provider.default_model,
        is_active=db_provider.is_active,
        api_key_configured=bool(db_provider.api_key),
        created_at=db_provider.created_at,
        updated_at=db_provider.updated_at
    )

@router.delete("/{provider_id}")
async def delete_provider(provider_id: UUID, db: Session = Depends(get_db)):
    """Delete an AI Provider configuration."""
    query = select(AIProvider).where(AIProvider.id == provider_id)
    result = await db.execute(query)
    provider = result.scalar_one_or_none()
    
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
        
    await db.delete(provider)
    await db.commit()
    return {"message": "Provider deleted successfully"}
