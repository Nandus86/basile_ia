"""
Workflows API — CRUD + Execution endpoints
"""
import logging
import time
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID

from app.database import get_db
from app.models.workflow import Workflow
from app.models.workflow_execution import WorkflowExecution
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate, WorkflowResponse, WorkflowList
from app.schemas.workflow_execution import (
    WorkflowExecuteRequest,
    WorkflowExecutionResponse,
    WorkflowExecutionList,
    WorkflowTestBlockRequest,
    WorkflowTestBlockResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────
# CRUD — Workflows
# ─────────────────────────────────────────────────────────────

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
    total = len(count_result.scalars().all())  # simplification

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

@router.post("/{workflow_id}/duplicate", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_workflow(workflow_id: UUID, db: AsyncSession = Depends(get_db)):
    """Duplicate a workflow including its agent access relations"""
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Create duplicated workflow
    new_workflow = Workflow(
        name=f"{workflow.name} (Cópia)",
        description=workflow.description,
        is_active=workflow.is_active,
        definition=workflow.definition,
        trigger_keywords=workflow.trigger_keywords,
        trigger_match_mode=workflow.trigger_match_mode,
        return_direct_payload=workflow.return_direct_payload,
    )

    db.add(new_workflow)
    await db.commit()
    await db.refresh(new_workflow)

    # Copy agent associations
    try:
        from app.models.agent import agent_workflow_access
        stmt = select(agent_workflow_access.c.agent_id).where(agent_workflow_access.c.workflow_id == workflow_id)
        agents_res = await db.execute(stmt)
        agent_ids = agents_res.scalars().all()

        for agent_id in agent_ids:
            await db.execute(
                agent_workflow_access.insert().values(
                    agent_id=agent_id,
                    workflow_id=new_workflow.id
                )
            )
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to copy agent associations for duplicated workflow: {e}")
        # Non-blocking: we still have the new workflow created

    return new_workflow


# ─────────────────────────────────────────────────────────────
# Execution — Run workflows
# ─────────────────────────────────────────────────────────────

@router.post("/{workflow_id}/execute", response_model=WorkflowExecutionResponse)
async def execute_workflow(
    workflow_id: UUID,
    request: WorkflowExecuteRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Execute a workflow synchronously.
    Returns the full execution result including accumulated context.
    """
    from app.services.workflow_engine import WorkflowEngine

    engine = WorkflowEngine(db)

    try:
        result_context = await engine.execute(
            workflow_id=workflow_id,
            trigger_data=request.trigger_data,
            trigger_type="manual",
        )

        # Check for early response
        if isinstance(result_context, dict) and result_context.get("status") == "early_response":
            exec_id = result_context.get("execution_id")
            next_block = result_context.get("current_block_id")
            early_result = result_context.get("result")
            # Schedule the remaining background execution
            background_tasks.add_task(engine.continue_background_execution, exec_id, next_block)
            
            # Return early to caller as if it's completed
            exec_result = await db.execute(select(WorkflowExecution).where(WorkflowExecution.id == exec_id))
            execution = exec_result.scalar_one_or_none()
            if execution:
                return WorkflowExecutionResponse(
                    id=execution.id,
                    workflow_id=execution.workflow_id,
                    status="completed",
                    result=early_result,
                    context=result_context.get("context", {}),
                    current_block_id=execution.current_block_id,
                    blocks_executed=execution.blocks_executed,
                    duration_ms=execution.duration_ms,
                    error_message=execution.error_message,
                    started_at=execution.started_at,
                    completed_at=execution.completed_at
                )

        # Fetch the execution record
        exec_result = await db.execute(
            select(WorkflowExecution)
            .where(WorkflowExecution.workflow_id == workflow_id)
            .order_by(WorkflowExecution.created_at.desc())
            .limit(1)
        )
        execution = exec_result.scalar_one_or_none()
        if execution:
            return execution

        # Fallback
        return WorkflowExecutionResponse(
            id=workflow_id,
            workflow_id=workflow_id,
            status="completed",
            context=result_context,
        )

    except Exception as e:
        logger.error(f"[Workflows API] Execution failed: {e}")
        # Fetch the failed execution record
        exec_result = await db.execute(
            select(WorkflowExecution)
            .where(WorkflowExecution.workflow_id == workflow_id)
            .order_by(WorkflowExecution.created_at.desc())
            .limit(1)
        )
        execution = exec_result.scalar_one_or_none()
        if execution:
            return execution

        raise HTTPException(status_code=500, detail=f"Workflow execution failed: {str(e)}")


@router.post("/{workflow_id}/execute/async")
async def execute_workflow_async(
    workflow_id: UUID,
    request: WorkflowExecuteRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Enqueue a workflow for asynchronous execution.
    Returns immediately with the execution ID.
    """
    import asyncio
    from app.services.workflow_engine import WorkflowEngine

    # Validate workflow exists
    wf_result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = wf_result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Create pending execution record
    execution = WorkflowExecution(
        workflow_id=workflow_id,
        status="pending",
        trigger_type="manual",
        trigger_data=request.trigger_data,
        context={},
        blocks_executed=[],
        blocks_total=len((workflow.definition or {}).get('blocks', [])),
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)

    # Launch in background
    async def _run_async():
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as bg_db:
            engine = WorkflowEngine(bg_db)
            try:
                await engine.execute(
                    workflow_id=workflow_id,
                    trigger_data=request.trigger_data,
                    trigger_type="manual",
                )
            except Exception as e:
                logger.error(f"[Workflows API] Async execution failed: {e}")

    asyncio.create_task(_run_async())

    return {
        "execution_id": str(execution.id),
        "status": "pending",
        "message": "Workflow enfileirado para execução",
    }


# ─────────────────────────────────────────────────────────────
# Execution Logs
# ─────────────────────────────────────────────────────────────

@router.get("/{workflow_id}/executions", response_model=WorkflowExecutionList)
async def list_workflow_executions(
    workflow_id: UUID,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List execution history for a workflow"""
    result = await db.execute(
        select(WorkflowExecution)
        .where(WorkflowExecution.workflow_id == workflow_id)
        .order_by(WorkflowExecution.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    executions = result.scalars().all()

    count_result = await db.execute(
        select(func.count(WorkflowExecution.id))
        .where(WorkflowExecution.workflow_id == workflow_id)
    )
    total = count_result.scalar() or 0

    return {"executions": executions, "total": total}


@router.get("/executions/{execution_id}", response_model=WorkflowExecutionResponse)
async def get_workflow_execution(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get details of a specific execution"""
    result = await db.execute(
        select(WorkflowExecution).where(WorkflowExecution.id == execution_id)
    )
    execution = result.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution


@router.delete("/executions/{execution_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow_execution(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete an execution log"""
    result = await db.execute(
        select(WorkflowExecution).where(WorkflowExecution.id == execution_id)
    )
    execution = result.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    await db.delete(execution)
    await db.commit()
    return None


# ─────────────────────────────────────────────────────────────
# Block Testing
# ─────────────────────────────────────────────────────────────

@router.post("/test-block", response_model=WorkflowTestBlockResponse)
async def test_single_block(
    request: WorkflowTestBlockRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Test a single block in isolation with a simulated context.
    Useful for debugging HTTP requests, conditions, transforms, etc.
    """
    from app.services.workflow_engine import WorkflowEngine

    engine = WorkflowEngine(db)
    t0 = time.time()

    try:
        result = await engine.execute_single_block(
            block=request.block,
            context=request.context,
        )
        duration_ms = (time.time() - t0) * 1000
        output_key = request.block.get('config', {}).get('output_key', request.block.get('id', 'test'))

        return WorkflowTestBlockResponse(
            success=True,
            output_key=output_key,
            result=result,
            duration_ms=duration_ms,
        )

    except Exception as e:
        duration_ms = (time.time() - t0) * 1000
        return WorkflowTestBlockResponse(
            success=False,
            error=str(e),
            duration_ms=duration_ms,
        )


@router.post("/executions/{execution_id}/resume", response_model=WorkflowExecutionResponse)
async def resume_workflow_execution(
    execution_id: UUID,
    request: WorkflowExecuteRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Resume a paused workflow execution synchronously.
    Returns the next state of the execution.
    """
    from app.services.workflow_engine import WorkflowEngine

    engine = WorkflowEngine(db)

    try:
        result_context = await engine.resume(
            execution_id=execution_id,
            input_data=request.trigger_data,
        )

        # Check for early response
        if isinstance(result_context, dict) and result_context.get("status") == "early_response":
            next_block = result_context.get("current_block_id")
            early_result = result_context.get("result")
            # Schedule the remaining background execution
            background_tasks.add_task(engine.continue_background_execution, execution_id, next_block)
            
            # Return early to caller as if it's completed
            result = await db.execute(select(WorkflowExecution).where(WorkflowExecution.id == execution_id))
            execution = result.scalar_one_or_none()
            if execution:
                return WorkflowExecutionResponse(
                    id=execution.id,
                    workflow_id=execution.workflow_id,
                    status="completed",
                    result=early_result,
                    context=result_context.get("context", {}),
                    current_block_id=execution.current_block_id,
                    blocks_executed=execution.blocks_executed,
                    duration_ms=execution.duration_ms,
                    error_message=execution.error_message,
                    started_at=execution.started_at,
                    completed_at=execution.completed_at
                )

        # Fetch the updated execution record
        result = await db.execute(
            select(WorkflowExecution).where(WorkflowExecution.id == execution_id)
        )
        execution = result.scalar_one_or_none()
        if execution:
            return execution

        # Fallback
        return WorkflowExecutionResponse(
            id=execution_id,
            workflow_id=execution_id,
            status=result_context.get("status", "completed"),
            context=result_context.get("context", {}),
        )

    except Exception as e:
        logger.error(f"[Workflows API] Resume failed: {e}")
        raise HTTPException(status_code=500, detail=f"Workflow resume failed: {str(e)}")

