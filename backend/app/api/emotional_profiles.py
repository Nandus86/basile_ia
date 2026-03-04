"""
Emotional Profile Endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from uuid import UUID

from app.database import get_db
from app.models.emotional_profile import EmotionalProfile, DEFAULT_EMOTIONAL_PROFILES
from app.schemas.emotional_profile import (
    EmotionalProfileCreate, EmotionalProfileUpdate,
    EmotionalProfileResponse, EmotionalProfileList
)

router = APIRouter()


@router.get("", response_model=EmotionalProfileList)
async def list_emotional_profiles(
    category: Optional[str] = None,
    is_active: Optional[bool] = True,
    db: AsyncSession = Depends(get_db)
):
    """List all emotional profiles with optional filtering"""
    query = select(EmotionalProfile)
    
    if is_active is not None:
        query = query.where(EmotionalProfile.is_active == is_active)
    
    if category is not None:
        query = query.where(EmotionalProfile.category == category)
    
    query = query.order_by(EmotionalProfile.category, EmotionalProfile.name)
    result = await db.execute(query)
    profiles = result.scalars().all()
    
    return EmotionalProfileList(profiles=profiles, total=len(profiles))


@router.get("/{profile_id}", response_model=EmotionalProfileResponse)
async def get_emotional_profile(
    profile_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific emotional profile by ID"""
    result = await db.execute(
        select(EmotionalProfile).where(EmotionalProfile.id == profile_id)
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Emotional profile not found"
        )
    
    return profile


@router.get("/code/{code}", response_model=EmotionalProfileResponse)
async def get_emotional_profile_by_code(
    code: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific emotional profile by code"""
    result = await db.execute(
        select(EmotionalProfile).where(EmotionalProfile.code == code)
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Emotional profile not found"
        )
    
    return profile


@router.post("", response_model=EmotionalProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_emotional_profile(
    profile_data: EmotionalProfileCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new custom emotional profile"""
    # Check if code already exists
    existing = await db.execute(
        select(EmotionalProfile).where(EmotionalProfile.code == profile_data.code)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile with this code already exists"
        )
    
    profile = EmotionalProfile(**profile_data.model_dump(), is_system=False)
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    
    return profile


@router.put("/{profile_id}", response_model=EmotionalProfileResponse)
async def update_emotional_profile(
    profile_id: UUID,
    profile_data: EmotionalProfileUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update an emotional profile (system profiles can only update limited fields)"""
    result = await db.execute(
        select(EmotionalProfile).where(EmotionalProfile.id == profile_id)
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Emotional profile not found"
        )
    
    # Update only provided fields
    update_data = profile_data.model_dump(exclude_unset=True)
    
    # System profiles can't have certain fields modified
    if profile.is_system:
        protected_fields = ["code", "category", "prompt_template"]
        for field in protected_fields:
            update_data.pop(field, None)
    
    for field, value in update_data.items():
        setattr(profile, field, value)
    
    await db.commit()
    await db.refresh(profile)
    
    return profile


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_emotional_profile(
    profile_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete an emotional profile (system profiles cannot be deleted)"""
    result = await db.execute(
        select(EmotionalProfile).where(EmotionalProfile.id == profile_id)
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Emotional profile not found"
        )
    
    if profile.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System profiles cannot be deleted"
        )
    
    await db.delete(profile)
    await db.commit()


@router.post("/seed", status_code=status.HTTP_201_CREATED)
async def seed_emotional_profiles(
    db: AsyncSession = Depends(get_db)
):
    """Seed default emotional profiles (creates only if they don't exist)"""
    created = 0
    skipped = 0
    
    for profile_data in DEFAULT_EMOTIONAL_PROFILES:
        # Check if already exists
        existing = await db.execute(
            select(EmotionalProfile).where(EmotionalProfile.code == profile_data["code"])
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue
        
        profile = EmotionalProfile(**profile_data)
        db.add(profile)
        created += 1
    
    await db.commit()
    
    return {
        "message": f"Seed completed",
        "created": created,
        "skipped": skipped,
        "total_defaults": len(DEFAULT_EMOTIONAL_PROFILES)
    }
