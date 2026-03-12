"""
Workflows API
"""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from app.database import get_db
from app.models.workflow import Workflow
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate, WorkflowResponse, WorkflowList

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("", response_model=WorkflowList)
async def list_workflows(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List all workflows"""
    result = await db.execute(select(Workflow).offset(skip).limit(limit))
    workflows = result.scalars().all()
    
    count_result = await db.execute(select(Workflow))
    total = len(count_result.scalars().all()) # simplification
    
    return {"workflows": workflows, "total": total}

@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get a specific workflow by ID"""
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
        
    return workflow

@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(workflow_in: WorkflowCreate, db: AsyncSession = Depends(get_db)):
    """Create a new workflow"""
    workflow = Workflow(**workflow_in.model_dump())
    
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)
    
    return workflow

@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: UUID,
    workflow_in: WorkflowUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a workflow"""
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
        
    update_data = workflow_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(workflow, key, value)
        
    await db.commit()
    await db.refresh(workflow)
    
    return workflow

@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(workflow_id: UUID, db: AsyncSession = Depends(get_db)):
    """Delete a workflow"""
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
        
    await db.delete(workflow)
    await db.commit()
    return None
