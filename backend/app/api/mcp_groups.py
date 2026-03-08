from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import List
from uuid import UUID

from app.database import get_db
from app.models.mcp_group import MCPGroup
from app.schemas.mcp_group import MCPGroupCreate, MCPGroupUpdate, MCPGroupResponse

router = APIRouter()

@router.get("", response_model=List[MCPGroupResponse])
async def list_mcp_groups(db: AsyncSession = Depends(get_db)):
    """List all MCP groups"""
    result = await db.execute(
        select(MCPGroup).order_by(MCPGroup.name)
    )
    return result.scalars().all()

@router.post("", response_model=MCPGroupResponse)
async def create_mcp_group(
    group_in: MCPGroupCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new MCP Group"""
    db_group = MCPGroup(**group_in.model_dump())
    db.add(db_group)
    try:
        await db.commit()
        await db.refresh(db_group)
        return db_group
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{group_id}", response_model=MCPGroupResponse)
async def update_mcp_group(
    group_id: UUID,
    group_in: MCPGroupUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update an MCP Group"""
    result = await db.execute(select(MCPGroup).filter(MCPGroup.id == group_id))
    db_group = result.scalar_one_or_none()
    
    if not db_group:
        raise HTTPException(status_code=404, detail="MCP Group not found")
        
    update_data = group_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_group, key, value)
        
    try:
        await db.commit()
        await db.refresh(db_group)
        return db_group
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{group_id}")
async def delete_mcp_group(
    group_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete an MCP Group"""
    result = await db.execute(select(MCPGroup).filter(MCPGroup.id == group_id))
    db_group = result.scalar_one_or_none()
    
    if not db_group:
        raise HTTPException(status_code=404, detail="MCP Group not found")
        
    try:
        await db.delete(db_group)
        await db.commit()
        return {"ok": True}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
