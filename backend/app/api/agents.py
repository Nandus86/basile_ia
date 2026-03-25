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
from app.models.mcp_group import MCPGroup
from app.models.skill import Skill
from app.models.information_base import InformationBase
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
        selectinload(Agent.mcp_groups),
        selectinload(Agent.skills),
        selectinload(Agent.information_bases),
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
            vector_memory_enabled=agent.vector_memory_enabled,
            training_memory_enabled=agent.training_memory_enabled,
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
            selectinload(Agent.mcp_groups),
            selectinload(Agent.skills),
            selectinload(Agent.information_bases),
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
        vector_memory_enabled=agent.vector_memory_enabled,
        training_memory_enabled=agent.training_memory_enabled,
        status_updates_enabled=agent.status_updates_enabled,
        status_updates_config=agent.status_updates_config,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
        mcps=[{"id": m.id, "name": m.name} for m in agent.mcps],
        mcp_groups=[{"id": g.id, "name": g.name, "description": g.description} for g in agent.mcp_groups],
        skills=[{"id": s.id, "name": s.name, "is_active": s.is_active} for s in agent.skills],
        information_bases=[{"id": ib.id, "name": ib.name, "is_active": ib.is_active} for ib in agent.information_bases],
        collaborators=collaborators
    )


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    agent_data: AgentCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new agent"""
    # Extract lists before creating agent
    mcp_ids = agent_data.mcp_ids or []
    mcp_group_ids = agent_data.mcp_group_ids or []
    skill_ids = agent_data.skill_ids or []
    agent_dict = agent_data.model_dump(exclude={"mcp_ids", "mcp_group_ids", "skill_ids"})
    
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
        
    # Link MCP Groups if provided
    if mcp_group_ids:
        grp_result = await db.execute(
            select(MCPGroup).where(MCPGroup.id.in_(mcp_group_ids))
        )
        groups = grp_result.scalars().all()
        agent.mcp_groups = list(groups)
    
    # Link Skills if provided
    if skill_ids:
        skill_result = await db.execute(
            select(Skill).where(Skill.id.in_(skill_ids))
        )
        skills = skill_result.scalars().all()
        agent.skills = list(skills)
    
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
        .options(selectinload(Agent.mcps), selectinload(Agent.mcp_groups))
        .where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )
    
    # Update only provided fields
    update_data = agent_data.model_dump(exclude_unset=True, exclude={"mcp_ids", "mcp_group_ids"})
    
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
        
    # Update MCP Groups if provided
    if hasattr(agent_data, 'mcp_group_ids') and agent_data.mcp_group_ids is not None:
        grp_result = await db.execute(
            select(MCPGroup).where(MCPGroup.id.in_(agent_data.mcp_group_ids))
        )
        groups = grp_result.scalars().all()
        agent.mcp_groups = list(groups)
        
    # Update Skills if provided
    if hasattr(agent_data, 'skill_ids') and agent_data.skill_ids is not None:
        skill_result = await db.execute(
            select(Skill).where(Skill.id.in_(agent_data.skill_ids))
        )
        skills = skill_result.scalars().all()
        agent.skills = list(skills)
        
    # Update Information Bases if provided
    if hasattr(agent_data, 'information_base_ids') and agent_data.information_base_ids is not None:
        ib_result = await db.execute(
            select(InformationBase).where(InformationBase.id.in_(agent_data.information_base_ids))
        )
        bases = ib_result.scalars().all()
        agent.information_bases = list(bases)
    
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
    # We must await flush here to actually remove them from the identity map
    # before we try to insert new ones with potentially the same keys.
    for setting in list(agent.collaborator_settings):
        # Prevent "already attached" by removing from collection
        agent.collaborator_settings.remove(setting)
        await db.delete(setting)
        
    await db.flush()
    
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


# ==================== Agent MCP Groups Endpoints ====================

class AgentMCPGroupItem(BaseModel):
    """MCP Group summary for agent"""
    id: UUID
    name: str
    description: Optional[str] = None

class AgentMCPGroupList(BaseModel):
    """List of MCP Groups for an agent"""
    agent_id: UUID
    agent_name: str
    mcp_groups: List[AgentMCPGroupItem]
    total: int


@router.get("/{agent_id}/mcp-groups", response_model=AgentMCPGroupList)
async def list_agent_mcp_groups(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """List all MCP Groups associated with an agent"""
    result = await db.execute(
        select(Agent)
        .options(selectinload(Agent.mcp_groups))
        .where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    group_items = [
        AgentMCPGroupItem(
            id=group.id,
            name=group.name,
            description=group.description
        )
        for group in agent.mcp_groups
    ]
    
    return AgentMCPGroupList(
        agent_id=agent.id,
        agent_name=agent.name,
        mcp_groups=group_items,
        total=len(group_items)
    )


@router.post("/{agent_id}/mcp-groups/{group_id}", response_model=AgentMCPGroupItem)
async def add_mcp_group_to_agent(
    agent_id: UUID,
    group_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Add an MCP Group to an agent"""
    # Check agent exists
    result = await db.execute(
        select(Agent).options(selectinload(Agent.mcp_groups)).where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Check MCP Group exists
    group_result = await db.execute(select(MCPGroup).where(MCPGroup.id == group_id))
    group = group_result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="MCP Group not found")
    
    # Check if already added
    if group in agent.mcp_groups:
        raise HTTPException(status_code=400, detail="MCP Group already associated with this agent")
    
    # Add group to agent
    agent.mcp_groups.append(group)
    await db.commit()
    
    return AgentMCPGroupItem(
        id=group.id,
        name=group.name,
        description=group.description
    )


@router.delete("/{agent_id}/mcp-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_mcp_group_from_agent(
    agent_id: UUID,
    group_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Remove an MCP Group from an agent"""
    # Check agent exists
    result = await db.execute(
        select(Agent).options(selectinload(Agent.mcp_groups)).where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Find and remove Group
    group_to_remove = None
    for group in agent.mcp_groups:
        if group.id == group_id:
            group_to_remove = group
            break
    
    if not group_to_remove:
        raise HTTPException(status_code=404, detail="MCP Group not associated with this agent")
    
    agent.mcp_groups.remove(group_to_remove)
    await db.commit()




# ==================== Agent Skills Endpoints ====================

class AgentSkillItem(BaseModel):
    """Skill summary for agent"""
    id: UUID
    name: str
    is_active: bool

class AgentSkillList(BaseModel):
    """List of Skills for an agent"""
    agent_id: UUID
    agent_name: str
    skills: List[AgentSkillItem]
    total: int


@router.get("/{agent_id}/skills", response_model=AgentSkillList)
async def list_agent_skills(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """List all Skills associated with an agent"""
    result = await db.execute(
        select(Agent)
        .options(selectinload(Agent.skills))
        .where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    skill_items = [
        AgentSkillItem(
            id=skill.id,
            name=skill.name,
            is_active=skill.is_active
        )
        for skill in agent.skills
    ]
    
    return AgentSkillList(
        agent_id=agent.id,
        agent_name=agent.name,
        skills=skill_items,
        total=len(skill_items)
    )


@router.post("/{agent_id}/skills/{skill_id}", response_model=AgentSkillItem)
async def add_skill_to_agent(
    agent_id: UUID,
    skill_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Add a Skill to an agent"""
    # Check agent exists
    result = await db.execute(
        select(Agent).options(selectinload(Agent.skills)).where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Check Skill exists
    skill_result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = skill_result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    # Check if already added
    if skill in agent.skills:
        raise HTTPException(status_code=400, detail="Skill already associated with this agent")
    
    # Add Skill to agent
    agent.skills.append(skill)
    await db.commit()
    
    return AgentSkillItem(
        id=skill.id,
        name=skill.name,
        is_active=skill.is_active
    )


@router.delete("/{agent_id}/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_skill_from_agent(
    agent_id: UUID,
    skill_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Remove a Skill from an agent"""
    # Check agent exists
    result = await db.execute(
        select(Agent).options(selectinload(Agent.skills)).where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Find and remove Skill
    skill_to_remove = None
    for skill in agent.skills:
        if skill.id == skill_id:
            skill_to_remove = skill
            break
    
    if not skill_to_remove:
        raise HTTPException(status_code=404, detail="Skill not associated with this agent")
    
    agent.skills.remove(skill_to_remove)
    await db.commit()


# ==================== Agent Information Bases Endpoints ====================

class AgentInfoBaseItem(BaseModel):
    """Information Base summary for agent"""
    id: UUID
    name: str
    is_active: bool

class AgentInfoBaseList(BaseModel):
    """List of Information Bases for an agent"""
    agent_id: UUID
    agent_name: str
    information_bases: List[AgentInfoBaseItem]
    total: int

@router.get("/{agent_id}/information-bases", response_model=AgentInfoBaseList)
async def list_agent_information_bases(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """List all Information Bases associated with an agent"""
    result = await db.execute(
        select(Agent)
        .options(selectinload(Agent.information_bases))
        .where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    ib_items = [
        AgentInfoBaseItem(
            id=ib.id,
            name=ib.name,
            is_active=ib.is_active
        )
        for ib in agent.information_bases
    ]
    
    return AgentInfoBaseList(
        agent_id=agent.id,
        agent_name=agent.name,
        information_bases=ib_items,
        total=len(ib_items)
    )

@router.post("/{agent_id}/information-bases/{base_id}", response_model=AgentInfoBaseItem)
async def add_information_base_to_agent(
    agent_id: UUID,
    base_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Add an Information Base to an agent"""
    # Check agent exists
    result = await db.execute(
        select(Agent).options(selectinload(Agent.information_bases)).where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Check Base exists
    ib_result = await db.execute(select(InformationBase).where(InformationBase.id == base_id))
    ib = ib_result.scalar_one_or_none()
    if not ib:
        raise HTTPException(status_code=404, detail="Information Base not found")
    
    # Check if already added
    if ib in agent.information_bases:
        raise HTTPException(status_code=400, detail="Information Base already associated with this agent")
    
    # Add to agent
    agent.information_bases.append(ib)
    await db.commit()
    
    return AgentInfoBaseItem(
        id=ib.id,
        name=ib.name,
        is_active=ib.is_active
    )

@router.delete("/{agent_id}/information-bases/{base_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_information_base_from_agent(
    agent_id: UUID,
    base_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Remove an Information Base from an agent"""
    # Check agent exists
    result = await db.execute(
        select(Agent).options(selectinload(Agent.information_bases)).where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Find and remove
    ib_to_remove = None
    for ib in agent.information_bases:
        if ib.id == base_id:
            ib_to_remove = ib
            break
    
    if not ib_to_remove:
        raise HTTPException(status_code=404, detail="Information Base not associated with this agent")
    
    agent.information_bases.remove(ib_to_remove)
    await db.commit()


# ==================== Agent VFS Knowledge Bases Endpoints (RAG 3.0) ====================

from app.models.vfs_knowledge_base import VFSKnowledgeBase

class AgentVFSItem(BaseModel):
    """VFS Knowledge Base summary for agent"""
    id: UUID
    name: str
    description: Optional[str] = None
    file_count: int = 0
    is_active: bool = True

class AgentVFSList(BaseModel):
    """List of VFS Knowledge Bases for an agent"""
    agent_id: UUID
    agent_name: str
    vfs_knowledge_bases: List[AgentVFSItem]
    total: int


@router.get("/{agent_id}/vfs-knowledge-bases", response_model=AgentVFSList)
async def list_agent_vfs_bases(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """List all VFS Knowledge Bases associated with an agent"""
    result = await db.execute(
        select(Agent)
        .options(selectinload(Agent.vfs_knowledge_bases))
        .where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    items = [
        AgentVFSItem(
            id=vfs.id,
            name=vfs.name,
            description=vfs.description,
            file_count=vfs.file_count or 0,
            is_active=vfs.is_active
        )
        for vfs in agent.vfs_knowledge_bases
    ]
    
    return AgentVFSList(
        agent_id=agent.id,
        agent_name=agent.name,
        vfs_knowledge_bases=items,
        total=len(items)
    )


@router.post("/{agent_id}/vfs-knowledge-bases/{kb_id}", response_model=AgentVFSItem)
async def add_vfs_base_to_agent(
    agent_id: UUID,
    kb_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Add a VFS Knowledge Base to an agent"""
    result = await db.execute(
        select(Agent).options(selectinload(Agent.vfs_knowledge_bases)).where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    kb_result = await db.execute(select(VFSKnowledgeBase).where(VFSKnowledgeBase.id == kb_id))
    kb = kb_result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="VFS Knowledge Base not found")

    if kb in agent.vfs_knowledge_bases:
        raise HTTPException(status_code=400, detail="VFS Knowledge Base already associated with this agent")

    agent.vfs_knowledge_bases.append(kb)
    await db.commit()

    return AgentVFSItem(
        id=kb.id,
        name=kb.name,
        description=kb.description,
        file_count=kb.file_count or 0,
        is_active=kb.is_active
    )


@router.delete("/{agent_id}/vfs-knowledge-bases/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_vfs_base_from_agent(
    agent_id: UUID,
    kb_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Remove a VFS Knowledge Base from an agent"""
    result = await db.execute(
        select(Agent).options(selectinload(Agent.vfs_knowledge_bases)).where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    kb_to_remove = None
    for kb in agent.vfs_knowledge_bases:
        if kb.id == kb_id:
            kb_to_remove = kb
            break

    if not kb_to_remove:
        raise HTTPException(status_code=404, detail="VFS Knowledge Base not associated with this agent")

    agent.vfs_knowledge_bases.remove(kb_to_remove)
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


# ==================== Prompt Preview Endpoint ====================

class PromptSection(BaseModel):
    """A section of the agent's prompt"""
    name: str
    content: str
    source: str  # config, skill, tools, system, rag, info_base, vector_memory, orchestrator
    estimated_tokens: int = 0

class PromptPreviewResponse(BaseModel):
    """Full prompt preview for an agent"""
    sections: List[PromptSection]
    total_estimated_tokens: int
    model: str


@router.get("/{agent_id}/prompt-preview")
async def get_prompt_preview(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Returns a static preview of all sections that compose the full prompt sent to the LLM.
    Dynamic sections (RAG, vector memory) show placeholder descriptions.
    """
    from app.models.vfs_knowledge_base import VFSKnowledgeBase
    from app.models.mcp_group import MCPGroup
    
    result = await db.execute(
        select(Agent)
        .options(
            selectinload(Agent.mcps),
            selectinload(Agent.mcp_groups).selectinload(MCPGroup.mcps),
            selectinload(Agent.skills),
            selectinload(Agent.information_bases),
            selectinload(Agent.collaborator_settings).selectinload(AgentCollaborator.collaborator),
            selectinload(Agent.emotional_profile),
            selectinload(Agent.documents),
            selectinload(Agent.vfs_knowledge_bases),
            selectinload(Agent.resilience_config),
        )
        .where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    sections = []
    
    def estimate_tokens(text: str) -> int:
        """Rough estimate: ~4 chars per token"""
        return len(text) // 4
    
    # 1. System Prompt Base
    if agent.system_prompt:
        sections.append(PromptSection(
            name="System Prompt Base",
            content=agent.system_prompt,
            source="config",
            estimated_tokens=estimate_tokens(agent.system_prompt)
        ))
    
    # 2. Emotional Profile
    if agent.emotional_profile:
        ep = agent.emotional_profile
        ep_text = f"Perfil Emocional: {ep.name} ({ep.category})\nIntensidade: {agent.emotional_intensity}"
        if hasattr(ep, 'prompt_instructions') and ep.prompt_instructions:
            ep_text += f"\n\n{ep.prompt_instructions}"
        sections.append(PromptSection(
            name=f"Perfil Emocional: {ep.name}",
            content=ep_text,
            source="config",
            estimated_tokens=estimate_tokens(ep_text)
        ))
    
    # 3. Skills
    active_skills = [s for s in (agent.skills or []) if s.is_active]
    if active_skills:
        for skill in active_skills:
            skill_text = f"## {skill.name}\n\n"
            if skill.intent:
                skill_text += f"**Intenção:** {skill.intent}\n\n"
            skill_text += skill.content_md or ""
            sections.append(PromptSection(
                name=f"Skill: {skill.name}",
                content=skill_text,
                source="skill",
                estimated_tokens=estimate_tokens(skill_text)
            ))
    
    # 4. Tools/MCPs
    all_mcps = list(agent.mcps or [])
    for group in (agent.mcp_groups or []):
        if hasattr(group, 'mcps') and group.mcps:
            all_mcps.extend(group.mcps)
    if all_mcps:
        tool_lines = []
        for mcp in all_mcps:
            protocol = getattr(mcp, 'protocol', 'http') or 'http'
            tool_lines.append(f"- **{mcp.name}** (protocolo: {protocol})")
        tools_text = "Ferramentas disponíveis para o agente:\n" + "\n".join(tool_lines)
        sections.append(PromptSection(
            name="Ferramentas / MCPs",
            content=tools_text,
            source="tools",
            estimated_tokens=estimate_tokens(tools_text)
        ))
    
    # 5. Input Schema
    if agent.input_schema:
        import json
        schema_text = "Esquema de entrada esperado (context_data):\n```json\n" + json.dumps(agent.input_schema, indent=2, ensure_ascii=False) + "\n```"
        sections.append(PromptSection(
            name="Input Schema",
            content=schema_text,
            source="config",
            estimated_tokens=estimate_tokens(schema_text)
        ))
    
    # 6. Output Schema
    if agent.output_schema:
        import json
        out_text = "Esquema de saída estruturada:\n```json\n" + json.dumps(agent.output_schema, indent=2, ensure_ascii=False) + "\n```"
        sections.append(PromptSection(
            name="Output Schema (Structured Output)",
            content=out_text,
            source="config",
            estimated_tokens=estimate_tokens(out_text)
        ))
    
    # 7. Resilience Config
    if agent.resilience_config:
        rc = agent.resilience_config
        rc_text = f"Configuração de Resiliência:\n- Max iterations: {getattr(rc, 'max_iterations', 'N/A')}\n- Timeout: {getattr(rc, 'timeout_seconds', 'N/A')}s"
        sections.append(PromptSection(
            name="Resiliência",
            content=rc_text,
            source="system",
            estimated_tokens=estimate_tokens(rc_text)
        ))
    
    # 8. Collaborators (if orchestrator)
    if agent.is_orchestrator and agent.collaborator_settings:
        collab_lines = []
        for setting in agent.collaborator_settings:
            collab = setting.collaborator
            status_icon = "✅" if setting.status.value == "enabled" else "⚪" if setting.status.value == "neutral" else "🚫"
            collab_lines.append(f"- {status_icon} **{collab.name}**: {collab.description or 'Sem descrição'} (status: {setting.status.value})")
        collab_text = "Agentes Especialistas (Colaboradores):\n" + "\n".join(collab_lines)
        sections.append(PromptSection(
            name="Orquestração: Colaboradores",
            content=collab_text,
            source="orchestrator",
            estimated_tokens=estimate_tokens(collab_text)
        ))
    
    # 9. Information Bases (dynamic — show placeholder)
    if agent.information_bases:
        ib_names = [ib.name for ib in agent.information_bases if ib.is_active]
        if ib_names:
            ib_text = f"Bases de informação ativas: {', '.join(ib_names)}\n\n[Conteúdo injetado dinamicamente com base na mensagem do usuário — pesquisa vetorial]"
            sections.append(PromptSection(
                name="Bases de Informação",
                content=ib_text,
                source="info_base",
                estimated_tokens=estimate_tokens(ib_text) + 200  # estimated dynamic content
            ))
    
    # 10. Documents / RAG (dynamic - show placeholder)
    if agent.documents:
        doc_names = [d.name for d in agent.documents]
        rag_text = f"Documentos RAG disponíveis: {', '.join(doc_names)}\n\n[Contexto injetado dinamicamente via busca semântica nos documentos]"
        sections.append(PromptSection(
            name="RAG (Documentos)",
            content=rag_text,
            source="rag",
            estimated_tokens=estimate_tokens(rag_text) + 500
        ))
    
    # 11. VFS Knowledge Bases (dynamic - show placeholder)
    if agent.vfs_knowledge_bases:
        vfs_names = [kb.name for kb in agent.vfs_knowledge_bases]
        vfs_text = f"VFS RAG 3.0 Knowledge Bases: {', '.join(vfs_names)}\n\n[Contexto injetado dinamicamente via VFS RAG 3.0]"
        sections.append(PromptSection(
            name="VFS RAG 3.0",
            content=vfs_text,
            source="rag",
            estimated_tokens=estimate_tokens(vfs_text) + 300
        ))
    
    # 12. Vector Memory (dynamic - show placeholder)
    if agent.vector_memory_enabled:
        vm_text = (
            "Memória Vetorial Inteligente: ATIVA\n\n"
            "Seções injetadas dinamicamente por prioridade:\n"
            "1. ⚠️ Correções do Usuário (PRIORIDADE MÁXIMA)\n"
            "2. 💡 Preferências do Usuário\n"
            "3. 📋 Fatos Qualitativos do Contato\n"
            "4. 🔧 Auto-Aprendizado do Agente (Lições Anteriores)\n\n"
            "[Conteúdo personalizado por contato/sessão via Weaviate]"
        )
        sections.append(PromptSection(
            name="Memória Vetorial Inteligente",
            content=vm_text,
            source="vector_memory",
            estimated_tokens=estimate_tokens(vm_text) + 200
        ))
    
    # 13. System context (date/time, etc.)
    sys_text = "Data/hora do sistema: [injetado dinamicamente]\nFuso horário configurado: America/Sao_Paulo"
    sections.append(PromptSection(
        name="Contexto do Sistema",
        content=sys_text,
        source="system",
        estimated_tokens=estimate_tokens(sys_text)
    ))
    
    total_tokens = sum(s.estimated_tokens for s in sections)
    
    return PromptPreviewResponse(
        sections=sections,
        total_estimated_tokens=total_tokens,
        model=agent.model or "gpt-4o-mini"
    )
