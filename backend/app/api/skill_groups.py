"""
Skill Groups API - CRUD for skill folder management
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from uuid import UUID

from app.database import get_db
from app.models.skill_group import SkillGroup
from app.schemas.skill_group import SkillGroupCreate, SkillGroupUpdate, SkillGroupResponse

router = APIRouter()


@router.get("", response_model=list[SkillGroupResponse])
async def list_skill_groups(db: AsyncSession = Depends(get_db)):
    """List all skill groups with item counts"""
    result = await db.execute(
        select(SkillGroup).order_by(SkillGroup.name)
    )
    groups = result.scalars().all()
    
    # Get counts
    from app.models.skill import Skill
    items = []
    for g in groups:
        count_result = await db.execute(
            select(func.count()).select_from(Skill).where(Skill.group_id == g.id)
        )
        count = count_result.scalar_one()
        items.append(SkillGroupResponse(
            id=g.id, name=g.name, description=g.description,
            is_active=g.is_active, created_at=g.created_at,
            updated_at=g.updated_at, skill_count=count
        ))
    return items


@router.post("", response_model=SkillGroupResponse, status_code=status.HTTP_201_CREATED)
async def create_skill_group(
    data: SkillGroupCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new skill group"""
    group = SkillGroup(**data.model_dump())
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return SkillGroupResponse(
        id=group.id, name=group.name, description=group.description,
        is_active=group.is_active, created_at=group.created_at,
        updated_at=group.updated_at, skill_count=0
    )


@router.put("/{group_id}", response_model=SkillGroupResponse)
async def update_skill_group(
    group_id: UUID,
    data: SkillGroupUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a skill group"""
    result = await db.execute(select(SkillGroup).where(SkillGroup.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Skill group not found")
    
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(group, key, value)
    
    await db.commit()
    await db.refresh(group)
    
    from app.models.skill import Skill
    count_result = await db.execute(
        select(func.count()).select_from(Skill).where(Skill.group_id == group.id)
    )
    return SkillGroupResponse(
        id=group.id, name=group.name, description=group.description,
        is_active=group.is_active, created_at=group.created_at,
        updated_at=group.updated_at, skill_count=count_result.scalar_one()
    )


@router.delete("/{group_id}")
async def delete_skill_group(
    group_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete a skill group (skills inside become ungrouped)"""
    result = await db.execute(select(SkillGroup).where(SkillGroup.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Skill group not found")
    
    await db.delete(group)
    await db.commit()
    return {"status": "deleted", "id": str(group_id)}
