"""
Skills API
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from uuid import UUID
import logging

from app.database import get_db
from app.models.skill import Skill
from app.schemas.skill import (
    SkillCreate,
    SkillUpdate,
    SkillResponse,
    SkillList,
    SkillGenerateRequest,
    SkillGenerateResponse
)
from app.config import settings

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=SkillList)
async def list_skills(
    skip: int = 0,
    limit: int = 100,
    search: str = None,
    group_id: UUID = None,
    db: AsyncSession = Depends(get_db)
):
    """List all available skills, optionally filtered by group"""
    query = select(Skill)
    
    if search:
        search_filter = or_(
            Skill.name.ilike(f"%{search}%"),
            Skill.intent.ilike(f"%{search}%")
        )
        query = query.where(search_filter)
    
    if group_id:
        query = query.where(Skill.group_id == group_id)
    else:
        query = query.where(Skill.group_id.is_(None))
        
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    # Get items
    query = query.order_by(Skill.name).offset(skip).limit(limit)
    result = await db.execute(query)
    skills = result.scalars().all()
    
    return {"skills": skills, "total": total}


@router.post("/", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
async def create_skill(
    skill_in: SkillCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new skill"""
    try:
        new_skill = Skill(
            name=skill_in.name,
            intent=skill_in.intent,
            content_md=skill_in.content_md,
            is_active=skill_in.is_active
        )
        db.add(new_skill)
        await db.commit()
        await db.refresh(new_skill)
        return new_skill
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating skill: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(
    skill_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific skill by ID"""
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
        
    return skill


@router.put("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: UUID,
    skill_in: SkillUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a skill"""
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
        
    try:
        update_data = skill_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(skill, field, value)
            
        await db.commit()
        await db.refresh(skill)
        return skill
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating skill {skill_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(
    skill_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete a skill"""
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
        
    try:
        await db.delete(skill)
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting skill {skill_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate", response_model=SkillGenerateResponse)
async def generate_skill(request: SkillGenerateRequest):
    """
    Generates an Anthropic-style SKILL.md file based on intent and name.
    Uses GPT-4o-mini to generate the markdown.
    """
    if not settings.OPENAI_API_KEY:
         raise HTTPException(status_code=500, detail="OPENAI_API_KEY não configurada no servidor.")

    try:
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=settings.OPENAI_API_KEY,
            temperature=0.7
        )

        system_prompt = '''Você é um especialista em criar 'Skills' para agentes de IA, seguindo a especificação SKILL.md da Anthropic.
A skill é um arquivo markdown com frontmatter YAML contendo o nome e a descrição, seguido de instruções detalhadas em markdown restringindo e guiando o comportamento do agente.

### REGRAS CRÍTICAS:
1. IDIOMA: Todas as instruções, fluxos de trabalho e conteúdo detalhado dentro do corpo do markdown DEVEM ser escritos em PORTUGUÊS (PT-BR). Mesmo que a solicitação do usuário esteja em outro idioma, o conteúdo gerado deve ser em português.
2. FORMATAÇÃO DE FERRAMENTA/SEÇÃO: Use cabeçalhos H2 para skills/tools e << >> para descrições de resumo:
   ## nome_da_capacidade
   << Breve resumo conciso desta seção em português >>

### NOVO FORMATO - FLUXO COM ETAPAS (OBRIGATÓRIO):
Cada skill deve ter etapas numeradas. Use os marcadores:
- <<FLOW_START>> ... <<FLOW_END>> para definir cada etapa do fluxo
- {{ $HITL }} APÓS o <<FLOW_END>> para pausar e esperar resposta do usuário

Formato exemplo:
## nome_da_capacidade
<< Resumo desta capability >>

Etapa 1
<<FLOW_START>>
[Ação da Etapa 1 - seja específico sobre o que fazer]
<<FLOW_END>>
{{ $HITL }}

Etapa 2
<<FLOW_START>>
[Ação da Etapa 2 - executada APÓS resposta do usuário na Etapa 1]
<<FLOW_END>>
{{ $HITL }}

Etapa 3
<<FLOW_START>>
[Ação da Etapa 3 - executada APÓS resposta do usuário na Etapa 2]
<<FLOW_END>>
Retorne o resultado

REGRAS DO FLUXO:
- Use {{ $HITL }} após cada etapa que precisa de informação do usuário
- NÃO use {{ $HITL }} na última etapa se não precisar de confirmação
- Cada etapa deve ser uma ação específica e clara
- Sempre pergunte informações necessárias ao usuário quando houver {{ $HITL }}

Seu objetivo é gerar APENAS o texto Markdown bruto para o arquivo `SKILL.md`, correspondendo à intenção do usuário. Não coloque nada antes ou depois do markdown. Não use blocos de código ```markdown.

A estrutura do output DEVE ser exatamente:
---
name: [Nome da Skill]
description: [Descrição curta e direta sobre quando o agente deve acionar esta skill]
---

# [Nome da Skill]

[Instruções gerais em PORTUGUÊS]

## Nome da Capacidade Primária
<< Resumo do que esta capability faz em português >>

Etapa 1
<<FLOW_START>>
[Ação clara e específica da Etapa 1]
<<FLOW_END>>
{{ $HITL }}

Etapa 2
<<FLOW_START>>
[Ação clara e específica da Etapa 2]
<<FLOW_END>>
{{ $HITL }}

Etapa 3
<<FLOW_START>>
[Ação clara e específica da Etapa 3]
<<FLOW_END>>
[Retorne o resultado]
'''

        humanprompt = f"Name of the skill: {request.name}\n\nWhat the skill should do (Intent): {request.intent}\n\nPlease generate the SKILL.md format."

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=humanprompt)
        ]

        response = await llm.ainvoke(messages)
        
        # Clean up markdown code blocks if the LLM added them despite instructions
        content = response.content.strip()
        if content.startswith("```markdown"):
            content = content[11:]
        elif content.startswith("```"):
            content = content[3:]
            
        if content.endswith("```"):
            content = content[:-3]
            
        content = content.strip()

        return SkillGenerateResponse(content_md=content)
    
    except Exception as e:
        logger.error(f"Error generating skill.md: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar a skill via LLM: {str(e)}")
