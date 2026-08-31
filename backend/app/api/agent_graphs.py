"""
Agent Graphs API Endpoints - CRUD and Interactive Testing for Multi-Agent Graphs
"""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID

from app.database import get_db
from app.models.agent_graph import AgentGraph
from app.models.agent import Agent
from app.schemas.agent_graph import (
    AgentGraphCreate,
    AgentGraphUpdate,
    AgentGraphResponse,
    AgentGraphSummary,
    AgentGraphList,
    AgentGraphExecuteRequest,
    AgentGraphExecuteResponse
)
from app.services.agent_graph_compiler import AgentGraphCompiler

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=AgentGraphList)
async def list_agent_graphs(
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db)
):
    """List all agent graphs with node counts and search filtering"""
    query = select(AgentGraph)

    if is_active is not None:
        query = query.where(AgentGraph.is_active == is_active)

    if search:
        query = query.where(AgentGraph.name.ilike(f"%{search}%"))

    query = query.order_by(AgentGraph.updated_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    graphs = result.scalars().all()

    # Build summaries
    summaries = []
    for g in graphs:
        definition = g.definition or {}
        nodes = definition.get("nodes", [])
        summaries.append(AgentGraphSummary(
            id=g.id,
            name=g.name,
            description=g.description,
            is_active=g.is_active,
            node_count=len(nodes),
            recursion_limit=g.recursion_limit,
            created_at=g.created_at,
            updated_at=g.updated_at
        ))

    # Total count
    count_query = select(func.count(AgentGraph.id))
    if is_active is not None:
        count_query = count_query.where(AgentGraph.is_active == is_active)
    if search:
        count_query = count_query.where(AgentGraph.name.ilike(f"%{search}%"))
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    return AgentGraphList(graphs=summaries, total=total)


@router.get("/{graph_id}", response_model=AgentGraphResponse)
async def get_agent_graph(
    graph_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific agent graph by ID"""
    result = await db.execute(select(AgentGraph).where(AgentGraph.id == graph_id))
    graph = result.scalar_one_or_none()

    if not graph:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Grafo de agentes não encontrado"
        )

    definition = graph.definition or {}
    nodes = definition.get("nodes", [])

    # Count assigned agents
    agent_count_res = await db.execute(
        select(func.count(Agent.id)).where(Agent.graph_id == graph_id)
    )
    assigned_count = agent_count_res.scalar_one()

    return AgentGraphResponse(
        id=graph.id,
        name=graph.name,
        description=graph.description,
        is_active=graph.is_active,
        definition=graph.definition or {},
        recursion_limit=graph.recursion_limit,
        timeout_seconds=graph.timeout_seconds,
        node_count=len(nodes),
        assigned_agent_count=assigned_count,
        created_at=graph.created_at,
        updated_at=graph.updated_at
    )


@router.post("", response_model=AgentGraphResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_graph(
    graph_in: AgentGraphCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new agent graph"""
    graph = AgentGraph(**graph_in.model_dump())
    db.add(graph)
    await db.commit()
    await db.refresh(graph)

    nodes = graph.definition.get("nodes", []) if graph.definition else []
    return AgentGraphResponse(
        id=graph.id,
        name=graph.name,
        description=graph.description,
        is_active=graph.is_active,
        definition=graph.definition or {},
        recursion_limit=graph.recursion_limit,
        timeout_seconds=graph.timeout_seconds,
        node_count=len(nodes),
        assigned_agent_count=0,
        created_at=graph.created_at,
        updated_at=graph.updated_at
    )


@router.put("/{graph_id}", response_model=AgentGraphResponse)
async def update_agent_graph(
    graph_id: UUID,
    graph_update: AgentGraphUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update an existing agent graph"""
    result = await db.execute(select(AgentGraph).where(AgentGraph.id == graph_id))
    graph = result.scalar_one_or_none()

    if not graph:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Grafo de agentes não encontrado"
        )

    update_data = graph_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(graph, field, value)

    await db.commit()
    await db.refresh(graph)

    nodes = graph.definition.get("nodes", []) if graph.definition else []
    agent_count_res = await db.execute(
        select(func.count(Agent.id)).where(Agent.graph_id == graph_id)
    )
    assigned_count = agent_count_res.scalar_one()

    return AgentGraphResponse(
        id=graph.id,
        name=graph.name,
        description=graph.description,
        is_active=graph.is_active,
        definition=graph.definition or {},
        recursion_limit=graph.recursion_limit,
        timeout_seconds=graph.timeout_seconds,
        node_count=len(nodes),
        assigned_agent_count=assigned_count,
        created_at=graph.created_at,
        updated_at=graph.updated_at
    )


@router.delete("/{graph_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent_graph(
    graph_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete an agent graph"""
    result = await db.execute(select(AgentGraph).where(AgentGraph.id == graph_id))
    graph = result.scalar_one_or_none()

    if not graph:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Grafo de agentes não encontrado"
        )

    await db.delete(graph)
    await db.commit()
    return None


@router.post("/{graph_id}/test", response_model=AgentGraphExecuteResponse)
async def test_agent_graph(
    graph_id: UUID,
    payload: AgentGraphExecuteRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Executes a test run of the agent graph with live step tracing,
    returning node execution timeline, latencies, and final response.
    """
    result = await db.execute(select(AgentGraph).where(AgentGraph.id == graph_id))
    graph = result.scalar_one_or_none()

    if not graph:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Grafo de agentes não encontrado"
        )

    compiler = AgentGraphCompiler(db)
    response = await compiler.execute_graph(
        graph=graph,
        message=payload.message,
        context_data=payload.context_data,
        session_id=payload.session_id,
        history=payload.history,
        override_definition=payload.definition
    )

    return response
