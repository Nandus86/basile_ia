"""
Agents CRUD Endpoints with Access Levels and Collaboration
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Optional, List
from uuid import UUID

from app.database import get_db
from app.models.agent import Agent, AgentCollaborator, CollaborationStatus, AccessLevel
from app.models.mcp import MCP
from app.schemas.agent import (
    AgentCreate, AgentUpdate, AgentResponse, AgentList, AgentListItem,
    CollaboratorsUpdateRequest, CollaboratorSummary, AccessLevelEnum, CollaborationStatusEnum
)

router = APIRouter()


@router.get("", response_model=AgentList)
async def list_agents(
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = None,
    access_level: Optional[AccessLevelEnum] = None,
    max_access_level: Optional[AccessLevelEnum] = Query(
        None, 
        description="Filter agents by maximum access level (for user filtering)"
    ),
    db: AsyncSession = Depends(get_db)
):
    """
    List all agents with optional filtering.
    
    - **access_level**: Filter by exact access level
    - **max_access_level**: Filter agents with level <= specified (for user permission filtering)
    """
    query = select(Agent).options(
        selectinload(Agent.mcps),
        selectinload(Agent.collaborator_settings)
    )
    
    if is_active is not None:
        query = query.where(Agent.is_active == is_active)
    
    if access_level is not None:
        query = query.where(Agent.access_level == AccessLevel(access_level.value))
    
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    agents = result.scalars().all()
    
    # Filter by max_access_level if provided
    if max_access_level is not None:
        max_level_value = AccessLevel.get_level_value(AccessLevel(max_access_level.value))
        agents = [
            a for a in agents 
            if AccessLevel.get_level_value(a.access_level) <= max_level_value
        ]
    
    # Build response with counts
    agent_items = []
    for agent in agents:
        agent_items.append(AgentListItem(
            id=agent.id,
            name=agent.name,
            description=agent.description,
            is_active=agent.is_active,
            access_level=AccessLevelEnum(agent.access_level.value),
            collaboration_enabled=agent.collaboration_enabled,
            is_orchestrator=agent.is_orchestrator,
            emotional_profile_id=agent.emotional_profile_id,
            mcp_count=len(agent.mcps) if agent.mcps else 0,
            collaborator_count=len(agent.collaborator_settings) if agent.collaborator_settings else 0,
            created_at=agent.created_at
        ))
    
    return AgentList(agents=agent_items, total=len(agent_items))


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific agent by ID with all relationships"""
    result = await db.execute(
        select(Agent)
        .options(
            selectinload(Agent.mcps),
            selectinload(Agent.collaborator_settings).selectinload(AgentCollaborator.collaborator),
            selectinload(Agent.emotional_profile)
        )
        .where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )
    
    # Build collaborators list
    collaborators = []
    for setting in agent.collaborator_settings:
        collaborators.append(CollaboratorSummary(
            id=setting.collaborator.id,
            name=setting.collaborator.name,
            status=setting.status.value
        ))
    
    # Build emotional profile summary
    emotional_profile_data = None
    if agent.emotional_profile:
        from app.schemas.emotional_profile import EmotionalProfileSummary
        emotional_profile_data = EmotionalProfileSummary(
            id=agent.emotional_profile.id,
            code=agent.emotional_profile.code,
            name=agent.emotional_profile.name,
            category=agent.emotional_profile.category,
            icon=agent.emotional_profile.icon,
            color=agent.emotional_profile.color
        )
    
    return AgentResponse(
        id=agent.id,
        name=agent.name,
        description=agent.description,
        system_prompt=agent.system_prompt,
        model=agent.model,
        temperature=agent.temperature,
        max_tokens=agent.max_tokens,
        config=agent.config,
        is_active=agent.is_active,
        access_level=AccessLevelEnum(agent.access_level.value),
        collaboration_enabled=agent.collaboration_enabled,
        is_orchestrator=agent.is_orchestrator,
        emotional_profile=emotional_profile_data,
        emotional_intensity=agent.emotional_intensity,
        output_schema=agent.output_schema,
        input_schema=agent.input_schema,
        transition_input_schema=agent.transition_input_schema,
        transition_output_schema=agent.transition_output_schema,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
        mcps=[{"id": m.id, "name": m.name} for m in agent.mcps],
        collaborators=collaborators
    )


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    agent_data: AgentCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new agent"""
    # Extract mcp_ids before creating agent
    mcp_ids = agent_data.mcp_ids or []
    agent_dict = agent_data.model_dump(exclude={"mcp_ids"})
    
    # Convert enum to model enum
    agent_dict["access_level"] = AccessLevel(agent_dict["access_level"].value)
    
    # Remove None FK values to avoid constraint issues
    if agent_dict.get("emotional_profile_id") is None:
        agent_dict.pop("emotional_profile_id", None)
    
    agent = Agent(**agent_dict)
    
    # Link MCPs if provided
    if mcp_ids:
        result = await db.execute(
            select(MCP).where(MCP.id.in_(mcp_ids))
        )
        mcps = result.scalars().all()
        agent.mcps = list(mcps)
    
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    
    return await get_agent(agent.id, db)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: UUID,
    agent_data: AgentUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update an existing agent"""
    result = await db.execute(
        select(Agent)
        .options(selectinload(Agent.mcps))
        .where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )
    
    # Update only provided fields
    update_data = agent_data.model_dump(exclude_unset=True, exclude={"mcp_ids"})
    
    # Handle access_level enum conversion
    if "access_level" in update_data and update_data["access_level"] is not None:
        update_data["access_level"] = AccessLevel(update_data["access_level"].value)
    
    for field, value in update_data.items():
        setattr(agent, field, value)
    
    # Update MCPs if provided
    if agent_data.mcp_ids is not None:
        mcp_result = await db.execute(
            select(MCP).where(MCP.id.in_(agent_data.mcp_ids))
        )
        mcps = mcp_result.scalars().all()
        agent.mcps = list(mcps)
    
    await db.commit()
    await db.refresh(agent)
    
    return await get_agent(agent.id, db)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete an agent"""
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )
    
    await db.delete(agent)
    await db.commit()


# ============== Collaboration Endpoints ==============

@router.get("/{agent_id}/collaborators", response_model=List[CollaboratorSummary])
async def get_collaborators(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get all collaborators for an agent"""
    result = await db.execute(
        select(Agent)
        .options(selectinload(Agent.collaborator_settings).selectinload(AgentCollaborator.collaborator))
        .where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )
    
    collaborators = []
    for setting in agent.collaborator_settings:
        collaborators.append(CollaboratorSummary(
            id=setting.collaborator.id,
            name=setting.collaborator.name,
            status=setting.status.value
        ))
    
    return collaborators


@router.put("/{agent_id}/collaborators", response_model=List[CollaboratorSummary])
async def update_collaborators(
    agent_id: UUID,
    request: CollaboratorsUpdateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Update collaborators for an agent"""
    # Verify agent exists
    result = await db.execute(
        select(Agent)
        .options(selectinload(Agent.collaborator_settings))
        .where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )
    
    # Delete existing collaborator settings
    for setting in agent.collaborator_settings:
        await db.delete(setting)
    
    # Create new settings
    for collab in request.collaborators:
        # Verify collaborator exists
        collab_result = await db.execute(
            select(Agent).where(Agent.id == collab.collaborator_id)
        )
        collaborator = collab_result.scalar_one_or_none()
        
        if not collaborator:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Collaborator {collab.collaborator_id} not found"
            )
        
        new_setting = AgentCollaborator(
            agent_id=agent_id,
            collaborator_id=collab.collaborator_id,
            status=CollaborationStatus(collab.status.value)
        )
        db.add(new_setting)
    
    await db.commit()
    
    return await get_collaborators(agent_id, db)


@router.post("/{agent_id}/collaborators/{collaborator_id}", response_model=CollaboratorSummary)
async def add_collaborator(
    agent_id: UUID,
    collaborator_id: UUID,
    status: CollaborationStatusEnum = CollaborationStatusEnum.NEUTRAL,
    db: AsyncSession = Depends(get_db)
):
    """Add a single collaborator to an agent"""
    # Verify both agents exist
    agent_result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = agent_result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    collab_result = await db.execute(select(Agent).where(Agent.id == collaborator_id))
    collaborator = collab_result.scalar_one_or_none()
    if not collaborator:
        raise HTTPException(status_code=404, detail="Collaborator not found")
    
    # Check if already exists
    existing = await db.execute(
        select(AgentCollaborator)
        .where(AgentCollaborator.agent_id == agent_id)
        .where(AgentCollaborator.collaborator_id == collaborator_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Collaborator already exists")
    
    # Create new setting
    setting = AgentCollaborator(
        agent_id=agent_id,
        collaborator_id=collaborator_id,
        status=CollaborationStatus(status.value)
    )
    db.add(setting)
    await db.commit()
    
    return CollaboratorSummary(
        id=collaborator.id,
        name=collaborator.name,
        status=status.value
    )


@router.delete("/{agent_id}/collaborators/{collaborator_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_collaborator(
    agent_id: UUID,
    collaborator_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Remove a collaborator from an agent"""
    result = await db.execute(
        select(AgentCollaborator)
        .where(AgentCollaborator.agent_id == agent_id)
        .where(AgentCollaborator.collaborator_id == collaborator_id)
    )
    setting = result.scalar_one_or_none()
    
    if not setting:
        raise HTTPException(status_code=404, detail="Collaborator setting not found")
    
    await db.delete(setting)
    await db.commit()


# ==================== Agent MCP Endpoints ====================

from pydantic import BaseModel

class AgentMCPItem(BaseModel):
    """MCP summary for agent"""
    id: UUID
    name: str
    protocol: str
    is_active: bool

class AgentMCPList(BaseModel):
    """List of MCPs for an agent"""
    agent_id: UUID
    agent_name: str
    mcps: List[AgentMCPItem]
    total: int


@router.get("/{agent_id}/mcps", response_model=AgentMCPList)
async def list_agent_mcps(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """List all MCPs associated with an agent"""
    result = await db.execute(
        select(Agent)
        .options(selectinload(Agent.mcps))
        .where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    mcp_items = [
        AgentMCPItem(
            id=mcp.id,
            name=mcp.name,
            protocol=mcp.protocol or "http",
            is_active=mcp.is_active
        )
        for mcp in agent.mcps
    ]
    
    return AgentMCPList(
        agent_id=agent.id,
        agent_name=agent.name,
        mcps=mcp_items,
        total=len(mcp_items)
    )


@router.post("/{agent_id}/mcps/{mcp_id}", response_model=AgentMCPItem)
async def add_mcp_to_agent(
    agent_id: UUID,
    mcp_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Add an MCP to an agent (gives agent access to use this MCP's tools)"""
    # Check agent exists
    result = await db.execute(
        select(Agent).options(selectinload(Agent.mcps)).where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Check MCP exists
    mcp_result = await db.execute(select(MCP).where(MCP.id == mcp_id))
    mcp = mcp_result.scalar_one_or_none()
    if not mcp:
        raise HTTPException(status_code=404, detail="MCP not found")
    
    # Check if already added
    if mcp in agent.mcps:
        raise HTTPException(status_code=400, detail="MCP already associated with this agent")
    
    # Add MCP to agent
    agent.mcps.append(mcp)
    await db.commit()
    
    return AgentMCPItem(
        id=mcp.id,
        name=mcp.name,
        protocol=mcp.protocol or "http",
        is_active=mcp.is_active
    )


@router.delete("/{agent_id}/mcps/{mcp_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_mcp_from_agent(
    agent_id: UUID,
    mcp_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Remove an MCP from an agent"""
    # Check agent exists
    result = await db.execute(
        select(Agent).options(selectinload(Agent.mcps)).where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Find and remove MCP
    mcp_to_remove = None
    for mcp in agent.mcps:
        if mcp.id == mcp_id:
            mcp_to_remove = mcp
            break
    
    if not mcp_to_remove:
        raise HTTPException(status_code=404, detail="MCP not associated with this agent")
    
    agent.mcps.remove(mcp_to_remove)
    await db.commit()


@router.get("/{agent_id}/tools")
async def list_agent_tools(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    List all tools available to an agent.
    This discovers tools from all MCPs associated with the agent.
    """
    from app.services.mcp_tools import MCPToolExecutor
    
    # Check agent exists
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    executor = MCPToolExecutor(db)
    mcps = await executor.get_agent_mcps(str(agent_id))
    
    all_tools = []
    for mcp in mcps:
        try:
            tools = await executor.discover_mcp_tools(mcp)
            for tool in tools:
                all_tools.append({
                    "name": tool.get("name"),
                    "description": tool.get("description", "")[:200],
                    "mcp_name": mcp.name,
                    "mcp_id": str(mcp.id),
                    "protocol": tool.get("protocol", mcp.protocol)
                })
        except Exception as e:
            all_tools.append({
                "name": f"error_{mcp.name}",
                "description": f"Failed to discover tools: {str(e)}",
                "mcp_name": mcp.name,
                "mcp_id": str(mcp.id),
                "protocol": mcp.protocol,
                "error": True
            })
    
    return {
        "agent_id": str(agent_id),
        "agent_name": agent.name,
        "tools": all_tools,
        "total": len(all_tools)
    }


# ==================== Agent Config Endpoints (Resilience) ====================

from app.models.agent_config import AgentConfig
from app.schemas.agent_config import AgentConfigCreate, AgentConfigUpdate, AgentConfigResponse


@router.get("/{agent_id}/config", response_model=AgentConfigResponse)
async def get_agent_config(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get agent resilience configuration"""
    result = await db.execute(
        select(Agent).options(selectinload(Agent.resilience_config)).where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    if not agent.resilience_config:
        # Create default config
        config = AgentConfig(agent_id=agent.id)
        db.add(config)
        await db.commit()
        await db.refresh(config)
        return config
    
    return agent.resilience_config


@router.put("/{agent_id}/config", response_model=AgentConfigResponse)
async def update_agent_config(
    agent_id: UUID,
    update: AgentConfigUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update agent resilience configuration"""
    result = await db.execute(
        select(Agent).options(selectinload(Agent.resilience_config)).where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    if not agent.resilience_config:
        # Create new config with updates
        config_data = update.model_dump(exclude_unset=True)
        config = AgentConfig(agent_id=agent.id, **config_data)
        db.add(config)
    else:
        # Update existing config
        for field, value in update.model_dump(exclude_unset=True).items():
            setattr(agent.resilience_config, field, value)
        config = agent.resilience_config
    
    await db.commit()
    await db.refresh(config)
    
    return config


# ==================== Agent Document Endpoints ====================

from app.models.document import Document


class AgentDocumentItem(BaseModel):
    """Document summary for agent"""
    id: UUID
    name: str
    file_type: str
    status: str
    chunk_count: int
    is_global: bool


class AgentDocumentList(BaseModel):
    """List of documents for an agent"""
    agent_id: UUID
    agent_name: str
    documents: List[AgentDocumentItem]
    total: int


@router.get("/{agent_id}/documents", response_model=AgentDocumentList)
async def list_agent_documents(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """List all documents associated with an agent"""
    result = await db.execute(
        select(Agent)
        .options(selectinload(Agent.documents))
        .where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Include global documents
    global_result = await db.execute(
        select(Document).where(Document.is_global == True).where(Document.is_active == True)
    )
    global_docs = global_result.scalars().all()
    
    # Combine agent docs with globals
    all_docs = list(agent.documents)
    doc_ids = {doc.id for doc in all_docs}
    for doc in global_docs:
        if doc.id not in doc_ids:
            all_docs.append(doc)
    
    doc_items = [
        AgentDocumentItem(
            id=doc.id,
            name=doc.name,
            file_type=doc.file_type,
            status=doc.status,
            chunk_count=doc.chunk_count,
            is_global=doc.is_global
        )
        for doc in all_docs if doc.is_active
    ]
    
    return AgentDocumentList(
        agent_id=agent.id,
        agent_name=agent.name,
        documents=doc_items,
        total=len(doc_items)
    )


@router.post("/{agent_id}/documents/{document_id}", response_model=AgentDocumentItem)
async def add_document_to_agent(
    agent_id: UUID,
    document_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Add a document to an agent (gives agent access to use this document for RAG)"""
    # Check agent exists
    result = await db.execute(
        select(Agent).options(selectinload(Agent.documents)).where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Check document exists
    doc_result = await db.execute(select(Document).where(Document.id == document_id))
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Check if already added
    if doc in agent.documents:
        raise HTTPException(status_code=400, detail="Document already associated with this agent")
    
    # Add document to agent
    agent.documents.append(doc)
    await db.commit()
    
    return AgentDocumentItem(
        id=doc.id,
        name=doc.name,
        file_type=doc.file_type,
        status=doc.status,
        chunk_count=doc.chunk_count,
        is_global=doc.is_global
    )


@router.delete("/{agent_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_document_from_agent(
    agent_id: UUID,
    document_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Remove a document from an agent"""
    # Check agent exists
    result = await db.execute(
        select(Agent).options(selectinload(Agent.documents)).where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Find and remove document
    doc_to_remove = None
    for doc in agent.documents:
        if doc.id == document_id:
            doc_to_remove = doc
            break
    
    if not doc_to_remove:
        raise HTTPException(status_code=404, detail="Document not associated with this agent")
    
    agent.documents.remove(doc_to_remove)
    await db.commit()
