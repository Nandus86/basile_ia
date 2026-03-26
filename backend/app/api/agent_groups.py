"""
Agent Groups API - CRUD for hierarchical agent folder management
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID

from app.database import get_db
from app.models.agent_group import AgentGroup
from app.models.agent import Agent
from app.schemas.agent_group import (
    AgentGroupCreate, AgentGroupUpdate, AgentGroupResponse, AgentGroupTree
)

router = APIRouter()


@router.get("", response_model=list[AgentGroupResponse])
async def list_agent_groups(
    parent_id: UUID = None,
    db: AsyncSession = Depends(get_db)
):
    """
    List agent groups. If parent_id is provided, returns children of that folder.
    If parent_id is null/omitted, returns root-level folders only.
    """
    query = select(AgentGroup)
    if parent_id is not None:
        query = query.where(AgentGroup.parent_id == parent_id)
    else:
        query = query.where(AgentGroup.parent_id.is_(None))
    
    query = query.order_by(AgentGroup.name)
    result = await db.execute(query)
    groups = result.scalars().all()
    
    items = []
    for g in groups:
        # Count agents in this group
        agent_count_result = await db.execute(
            select(func.count()).select_from(Agent).where(Agent.group_id == g.id)
        )
        # Count direct children folders
        children_count_result = await db.execute(
            select(func.count()).select_from(AgentGroup).where(AgentGroup.parent_id == g.id)
        )
        items.append(AgentGroupResponse(
            id=g.id, name=g.name, description=g.description,
            is_active=g.is_active, parent_id=g.parent_id,
            created_at=g.created_at, updated_at=g.updated_at,
            agent_count=agent_count_result.scalar_one(),
            children_count=children_count_result.scalar_one()
        ))
    return items


@router.get("/tree", response_model=list[AgentGroupTree])
async def get_agent_groups_tree(db: AsyncSession = Depends(get_db)):
    """Get the full folder tree for agents"""
    result = await db.execute(
        select(AgentGroup).order_by(AgentGroup.name)
    )
    all_groups = result.scalars().all()
    
    # Build tree
    by_parent = {}
    for g in all_groups:
        by_parent.setdefault(str(g.parent_id) if g.parent_id else None, []).append(g)
    
    def build_tree(parent_id=None):
        items = []
        for g in by_parent.get(parent_id, []):
            children = build_tree(str(g.id))
            items.append(AgentGroupTree(
                id=g.id, name=g.name, description=g.description,
                is_active=g.is_active, parent_id=g.parent_id,
                created_at=g.created_at, updated_at=g.updated_at,
                agent_count=0, children_count=len(children),
                children=children
            ))
        return items
    
    return build_tree()


@router.post("", response_model=AgentGroupResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_group(
    data: AgentGroupCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new agent group (folder)"""
    # Validate parent exists if provided
    if data.parent_id:
        parent_result = await db.execute(
            select(AgentGroup).where(AgentGroup.id == data.parent_id)
        )
        if not parent_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Parent folder not found")
    
    group = AgentGroup(**data.model_dump())
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return AgentGroupResponse(
        id=group.id, name=group.name, description=group.description,
        is_active=group.is_active, parent_id=group.parent_id,
        created_at=group.created_at, updated_at=group.updated_at,
        agent_count=0, children_count=0
    )


@router.put("/{group_id}", response_model=AgentGroupResponse)
async def update_agent_group(
    group_id: UUID,
    data: AgentGroupUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update an agent group"""
    result = await db.execute(select(AgentGroup).where(AgentGroup.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Agent group not found")
    
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(group, key, value)
    
    await db.commit()
    await db.refresh(group)
    
    agent_count_result = await db.execute(
        select(func.count()).select_from(Agent).where(Agent.group_id == group.id)
    )
    children_count_result = await db.execute(
        select(func.count()).select_from(AgentGroup).where(AgentGroup.parent_id == group.id)
    )
    return AgentGroupResponse(
        id=group.id, name=group.name, description=group.description,
        is_active=group.is_active, parent_id=group.parent_id,
        created_at=group.created_at, updated_at=group.updated_at,
        agent_count=agent_count_result.scalar_one(),
        children_count=children_count_result.scalar_one()
    )


@router.delete("/{group_id}")
async def delete_agent_group(
    group_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete an agent group and all sub-folders (CASCADE).
    Agents inside become ungrouped (SET NULL).
    """
    result = await db.execute(select(AgentGroup).where(AgentGroup.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Agent group not found")
    
    await db.delete(group)
    await db.commit()
    return {"status": "deleted", "id": str(group_id)}
