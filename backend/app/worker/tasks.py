"""
ARQ Task Definitions — v0.0.7 Agent-First Architecture
These functions run inside the ARQ worker process, decoupled from the FastAPI request.

Flow:
  Webhook (agent_id) → tasks.py → Agent executes directly
                                   ├── If is_orchestrator: consult collaborators first
                                   └── If not: respond as self
  (Supervisor only used as fallback when no agent_id is provided)
"""
import time
import json
from typing import Optional, Dict, Any, List

from app.database import AsyncSessionLocal
from app.redis_client import redis_client
from app.config import settings


# ─────────────────────────────────────────────────────────────
# Shared enrichment helper
# ─────────────────────────────────────────────────────────────

async def _enrich_agent_prompt(
    db,
    agent_config: Dict[str, Any],
    agent_id: str,
    message: str,
    session_id: str,
    context_data: Optional[Dict[str, Any]] = None,
    history: Optional[list] = None,
    transition_data: Optional[Dict[str, Any]] = None,
):
    """
    Enrich an agent's system_prompt with all contextual data:
      1. RAG (document knowledge base)
      2. Information Bases (Weaviate external data)
      3. Vector Memory (qualitative contact facts)
      4. Orchestrator pre-consultation (if is_orchestrator)
    
    Mutates agent_config["system_prompt"] in place and returns rag_context.
    """
    rag_context = None

    # Resolve dynamically provided timezone from transition_data if available
    tz_name = 'America/Sao_Paulo'
    if transition_data:
        # Check direct top-level string first for simplicity
        if isinstance(transition_data.get('zoneName'), str):
            tz_name = transition_data.get('zoneName')
        else:
            # Fallback to nested safely: church -> address -> timezone -> zoneName
            church_dict = transition_data.get('church', {})
            if isinstance(church_dict, dict):
                address_dict = church_dict.get('address', {})
                if isinstance(address_dict, dict):
                    timezone_dict = address_dict.get('timezone', {})
                    if isinstance(timezone_dict, dict):
                        zone_val = timezone_dict.get('zoneName')
                        if zone_val and isinstance(zone_val, str):
                            tz_name = zone_val

    # Inject CURRENT DATETIME as the very first contextual item
    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    except ImportError:
        # Fallback to pytz just in case the environment is somehow older
        import pytz
        ZoneInfo = pytz.timezone
        ZoneInfoNotFoundError = pytz.UnknownTimeZoneError
    
    try:
        user_tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        user_tz = ZoneInfo('America/Sao_Paulo')

    now = datetime.now(user_tz)
    current_time_str = now.strftime(f'%d/%m/%Y %H:%M:%S (Fuso: {tz_name})')
    current_iso = now.isoformat()
    
    agent_config["system_prompt"] = agent_config.get("system_prompt", "") + (
        f"\n\n## Data e Hora Local do Sistema\n"
        f"Abaixo estão os dados temporais deste exato momento. "
        f"Use isso para calcular prazos, responder se é dia/noite ou comparar com "
        f"as datas gravadas nas memórias (que também possuem timestamp).\n"
        f"- Data/Hora legível: {current_time_str}\n"
        f"- Timestamp ISO: {current_iso}\n"
    )

    # 1. RAG Context
    try:
        from app.services.rag_service import get_rag_context
        rag_context = await get_rag_context(db, agent_id, message, limit=5)
        if rag_context:
            print(f"[Task] 📚 RAG context loaded for {agent_config['name']}")
    except Exception as e:
        print(f"[Task] RAG error: {e}")

    # 1.5. VFS RAG 3.0 (Subagent Knowledge Retrieval)
    try:
        from app.services.vfs_rag_service import get_vfs_context
        vfs_context = await get_vfs_context(db, agent_id, message)
        if vfs_context:
            print(f"[Task] 📂 VFS RAG 3.0 context loaded for {agent_config['name']}")
            agent_config["system_prompt"] = agent_config.get("system_prompt", "") + (
                f"\n\n## Base de Conhecimento VFS (RAG 3.0)\n\n"
                f"As seguintes informações foram recuperadas da base de conhecimento VFS por um subagente especializado:\n\n"
                f"{vfs_context}\n"
            )
    except Exception as e:
        print(f"[Task] VFS RAG 3.0 error: {e}")

    # 2. Information Bases
    try:
        from app.models.agent import Agent as AgentModel
        from sqlalchemy import select as sa_select
        from sqlalchemy.orm import selectinload
        from app.weaviate_client import get_weaviate

        ib_result = await db.execute(
            sa_select(AgentModel)
            .options(selectinload(AgentModel.information_bases))
            .where(AgentModel.id == agent_id)
        )
        ib_agent = ib_result.scalar_one_or_none()
        if ib_agent and ib_agent.information_bases:
            active_bases = [b for b in ib_agent.information_bases if b.is_active]
            if active_bases:
                ctx = context_data or {}
                weaviate_cl = get_weaviate()
                all_info_nodes = []
                
                if weaviate_cl:
                    for ib in active_bases:
                        possible_ids = []
                        # Try extraction via correlation_schema
                        if ib.correlation_schema and isinstance(ib.correlation_schema, dict):
                            target_key = ib.correlation_schema.get("target")
                            if target_key:
                                parts = target_key.split(".")
                                val = ctx
                                for part in parts:
                                    if isinstance(val, dict) and part in val:
                                        val = val[part]
                                    else:
                                        val = None
                                        break
                                if val is not None and not isinstance(val, (dict, list)):
                                    v_str = str(val).strip()
                                    if v_str:
                                        possible_ids.append(v_str)
                        
                        # Fallback to general context scanning if no specific id was found
                        if not possible_ids:
                            for k, v in ctx.items():
                                if isinstance(v, str) and v.strip():
                                    possible_ids.append(v.strip())
                            if session_id:
                                possible_ids.append(str(session_id))
                        
                        # Fetch nodes uniquely for this base's IDs
                        for uid in possible_ids:
                            info_nodes = await weaviate_cl.search_information_bases(
                                base_codes=[ib.code], user_id=uid, query=message, limit=5
                            )
                            if info_nodes:
                                all_info_nodes.extend(info_nodes)
                                
                    if all_info_nodes:
                        seen = set()
                        unique_nodes = [
                            n for n in all_info_nodes
                            if n["content"] not in seen and not seen.add(n["content"])
                        ]
                        print(f"[Task] 📚 Retrieved {len(unique_nodes)} Information Base contexts")
                        info_str = "\n".join(
                            [f"- {n['content']} (Meta: {n['metadata']})" for n in unique_nodes[:10]]
                        )
                        agent_config["system_prompt"] = agent_config.get("system_prompt", "") + (
                            f"\n\n## Contextualização Personalizada Externa\n\n"
                            f"Informações anexadas aos bancos de dados do usuário logado:\n{info_str}\n"
                        )
    except Exception as ib_err:
        print(f"[Task] Failed to retrieve Information Bases: {ib_err}")

    # 3. Vector Memory (contact-level + agent-level)
    vector_memory_enabled = getattr(agent_config.get("agent_model"), "vector_memory_enabled", False)
    if vector_memory_enabled and agent_id and session_id:
        try:
            from app.weaviate_client import get_weaviate
            weaviate_client = get_weaviate()
            if weaviate_client:
                # 3a. Corrections & Preferences (HIGH PRIORITY — separate section)
                corrections = await weaviate_client.search_contact_memories(
                    agent_id=str(agent_id),
                    contact_id=str(session_id),
                    query=message,
                    limit=5,
                    memory_type="correction"
                )
                preferences = await weaviate_client.search_contact_memories(
                    agent_id=str(agent_id),
                    contact_id=str(session_id),
                    query=message,
                    limit=3,
                    memory_type="preference"
                )
                priority_items = corrections + preferences
                if priority_items:
                    print(f"[Task] ⚠️ Retrieved {len(corrections)} corrections + {len(preferences)} preferences for contact {session_id}")
                    priority_lines = [f"- {m['content']}" for m in priority_items]
                    priority_str = "\n".join(priority_lines)
                    agent_config["system_prompt"] = agent_config.get("system_prompt", "") + (
                        f"\n\n## ⚠️ Correções e Preferências do Usuário (PRIORIDADE MÁXIMA)\n\n"
                        f"As seguintes correções e preferências foram feitas PELO PRÓPRIO USUÁRIO. "
                        f"NUNCA repita os erros corrigidos abaixo. Respeite as preferências SEMPRE:\n\n"
                        f"{priority_str}\n"
                    )

                # 3b. General facts (normal priority)
                facts = await weaviate_client.search_contact_memories(
                    agent_id=str(agent_id),
                    contact_id=str(session_id),
                    query=message,
                    limit=5,
                    memory_type="fact"
                )
                if facts:
                    print(f"[Task] 🧠 Retrieved {len(facts)} qualitative facts for contact {session_id}")
                    mem_lines = []
                    for m in facts:
                        ts = m.get('created_at')
                        if ts:
                            try:
                                from datetime import datetime
                                if isinstance(ts, str):
                                    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                                else:
                                    dt = ts
                                date_str = dt.strftime('%d/%m/%Y')
                            except Exception:
                                date_str = str(ts)[:10]
                        else:
                            date_str = '—'
                        mem_lines.append(f"- [{date_str}] {m['content']}")
                    mem_str = "\n".join(mem_lines)
                    agent_config["system_prompt"] = agent_config.get("system_prompt", "") + (
                        f"\n\n## Inteligência e Memória Histórica do Contato\n\n"
                        f"Abaixo estão informações e peculiaridades qualitativas deste usuário, "
                        f"adquiridas em interações anteriores. A data entre colchetes indica quando o fato foi registrado. "
                        f"Utilize isso para personalizar ativamente o engajamento de maneira natural:\n\n"
                        f"{mem_str}\n"
                    )

                # 3c. Agent self-memories (agent-level learning)
                agent_self_memories = await weaviate_client.search_agent_self_memories(
                    agent_id=str(agent_id),
                    query=message,
                    limit=5,
                )
                if agent_self_memories:
                    print(f"[Task] 🔧 Retrieved {len(agent_self_memories)} agent self-memories")
                    self_lines = [f"- {m['content']}" for m in agent_self_memories]
                    self_str = "\n".join(self_lines)
                    agent_config["system_prompt"] = agent_config.get("system_prompt", "") + (
                        f"\n\n## 🔧 Auto-Aprendizado do Agente (Lições Anteriores)\n\n"
                        f"Em interações passadas, você cometeu os erros abaixo e aprendeu a corrigi-los. "
                        f"NÃO repita esses erros:\n\n"
                        f"{self_str}\n"
                    )

        except Exception as e:
            print(f"[Task] Failed to retrieve vector memory: {e}")

        # Extract new vector memories in background
        try:
            from app.services.vector_memory_service import extract_and_save_memories
            import asyncio

            history_copy = (history or [])[:]
            asyncio.create_task(
                extract_and_save_memories(
                    agent_id=str(agent_id),
                    contact_id=str(session_id),
                    history=history_copy,
                    current_message=message,
                )
            )
        except Exception as e:
            print(f"[Task] Failed to launch extraction task: {e}")

    # 4. Collaboration handling
    agent_model = agent_config.get("agent_model")
    is_orchestrator = getattr(agent_model, "is_orchestrator", False) if agent_model else False
    has_collaboration = getattr(agent_model, "collaboration_enabled", False) if agent_model else False
    
    if agent_model and is_orchestrator and has_collaboration:
        # v0.0.9: Orchestrator agents get collaborators as TOOLS
        # The ReAct agent naturally decides when to call each one
        print(f"[Task] 🔄 Orchestrator '{agent_config['name']}' — loading collaborator tools")
        try:
            collab_tools = await _build_collaborator_tools(db, agent_model, message, context_data)
            if collab_tools:
                existing_tools = agent_config.get("tools", []) or []
                agent_config["tools"] = existing_tools + collab_tools
                agent_config["has_tools"] = True
                print(f"[Task] 🎭 Added {len(collab_tools)} collaborator tools to '{agent_config['name']}'")
                
                # Add orchestration instructions to system prompt
                collab_names = [t.name for t in collab_tools]
                agent_config["system_prompt"] = agent_config.get("system_prompt", "") + (
                    f"\n\n## Agentes Especialistas Disponíveis\n\n"
                    f"Você tem acesso a agentes especialistas que podem ser acionados como ferramentas. "
                    f"Use-os quando a solicitação do usuário exigir uma especialidade que eles possuem.\n"
                    f"Agentes disponíveis: {', '.join(collab_names)}\n\n"
                    f"DIRETRIZES DE ORQUESTRAÇÃO (OBRIGATÓRIO):\n"
                    f"1. ANÁLISE: Antes de chamar um especialista, avalie se a solicitação realmente requer expertise externa.\n"
                    f"2. INSTRUÇÃO CLARA: Ao acionar um especialista, envie uma instrução técnica e direta do que ele deve resolver. Inclua contexto relevante.\n"
                    f"3. SÍNTESE OBRIGATÓRIA: Após obter respostas dos especialistas, você DEVE sintetizar e compor sua resposta final. NUNCA simplesmente repasse a resposta do especialista sem tratamento.\n"
                    f"4. RESPOSTA FINAL: Se sua instrução principal exige um especialista de 'Resposta Final', você DEVE chamá-lo para formatar o texto final antes de encerrar.\n"
                    f"5. HIERARQUIA: Você é o COORDENADOR. Os especialistas reportam a VOCÊ, não ao usuário final. Você é responsável pela qualidade da resposta final.\n"
                    f"6. NÃO REDUNDÂNCIA: Se você já possui informação suficiente na conversa ou no contexto, NÃO acione especialistas desnecessariamente.\n"
                )

        except Exception as e:
            import traceback
            print(f"[Task] Error loading collaborator tools: {e}")
            traceback.print_exc()
    elif agent_model and has_collaboration and not is_orchestrator:
        # Non-orchestrator agents: keep old pre-consultation
        print(f"[Task] 🔍 Pre-consultation for non-orchestrator agent '{agent_config['name']}'")
        try:
            from app.orchestrator.agent_orchestrator import AgentOrchestrator

            orchestrator = AgentOrchestrator(db)
            subordinate_context = await orchestrator.gather_subordinate_responses(
                message=message,
                primary_agent=agent_model,
                context=rag_context or "",
                context_data=context_data,
                history=history,
                session_id=session_id,
            )
            if subordinate_context:
                print(f"[Task] 🎭 Pre-consult loaded for {agent_config['name']}")
                agent_config["system_prompt"] = agent_config.get("system_prompt", "") + (
                    f"\n\n## Colaboradores (Subordinados)\n"
                    f"Os seguintes especialistas forneceram análises sobre a solicitação do usuário. "
                    f"Sintetize e utilize as informações relevantes para construir a resposta final:\n"
                    f"{subordinate_context}\n"
                )
        except Exception as e:
            import traceback
            print(f"[Task] Orchestrator pre-consultation error: {e}")
            traceback.print_exc()
    else:
        print(f"[Task] 🔍 SKIPPING collaboration (not applicable)")

    return rag_context


# ─────────────────────────────────────────────────────────────
# STM helper
# ─────────────────────────────────────────────────────────────

def _resolve_stm_config(agent_config: Optional[Dict[str, Any]]):
    """Returns (stm_enabled, stm_ttl_seconds)"""
    stm_enabled = True
    stm_ttl_seconds = 86400
    if agent_config and "config" in agent_config:
        cfg = agent_config["config"]
        stm_enabled = cfg.get("short_term_memory_enabled", True)
        stm_ttl_hours = cfg.get("short_term_memory_ttl_hours", 24)
        stm_ttl_seconds = int(stm_ttl_hours * 3600)
    return stm_enabled, stm_ttl_seconds


# ─────────────────────────────────────────────────────────────
# MTM (Medium-Term Memory) helpers — PostgreSQL
# ─────────────────────────────────────────────────────────────

async def _save_mtm_message(db, agent_id: str, session_id: str, role: str, content: str):
    """Save a message to MTM (PostgreSQL) and trigger auto-summarize if needed."""
    try:
        from app.models.conversation_message import ConversationMessage
        from sqlalchemy import func, select
        import uuid

        msg = ConversationMessage(
            id=uuid.uuid4(),
            agent_id=uuid.UUID(str(agent_id)),
            session_id=str(session_id),
            role=role,
            content=content,
        )
        db.add(msg)
        await db.commit()

        # Check if we crossed the 100-message threshold for auto-summarize
        count_q = select(func.count()).where(
            ConversationMessage.agent_id == uuid.UUID(str(agent_id)),
            ConversationMessage.session_id == str(session_id),
        )
        result = await db.execute(count_q)
        total = result.scalar() or 0

        if total > 0 and total % 100 == 0:
            print(f"[MTM] 📊 {total} messages for session {session_id}, triggering auto-summarize → LTM")
            import asyncio
            asyncio.create_task(_auto_summarize_mtm_to_ltm(db, agent_id, session_id))

    except Exception as e:
        print(f"[MTM] ❌ Error saving message: {e}")


async def _load_mtm_fallback(db, agent_id: str, session_id: str, limit: int = 5) -> list:
    """Load last N messages from MTM when STM is empty."""
    try:
        from app.models.conversation_message import ConversationMessage
        from sqlalchemy import select
        import uuid

        q = (
            select(ConversationMessage)
            .where(
                ConversationMessage.agent_id == uuid.UUID(str(agent_id)),
                ConversationMessage.session_id == str(session_id),
            )
            .order_by(ConversationMessage.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(q)
        rows = result.scalars().all()
        # Reverse to get chronological order
        rows = list(reversed(rows))
        return [
            {
                "role": r.role,
                "content": r.content,
                "timestamp": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    except Exception as e:
        print(f"[MTM] ❌ Error loading fallback: {e}")
        return []


async def _check_mtm_has_history(db, agent_id: str, session_id: str) -> bool:
    """Check if this contact has any prior conversation in MTM."""
    try:
        from app.models.conversation_message import ConversationMessage
        from sqlalchemy import select, func
        import uuid

        q = select(func.count()).where(
            ConversationMessage.agent_id == uuid.UUID(str(agent_id)),
            ConversationMessage.session_id == str(session_id),
        )
        result = await db.execute(q)
        return (result.scalar() or 0) > 0
    except Exception:
        return False


async def _auto_summarize_mtm_to_ltm(db, agent_id: str, session_id: str):
    """Auto-summarize MTM conversation into qualitative LTM facts."""
    try:
        from app.models.conversation_message import ConversationMessage
        from sqlalchemy import select
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage
        from app.weaviate_client import get_weaviate
        import uuid

        # Load all messages
        q = (
            select(ConversationMessage)
            .where(
                ConversationMessage.agent_id == uuid.UUID(str(agent_id)),
                ConversationMessage.session_id == str(session_id),
            )
            .order_by(ConversationMessage.created_at.asc())
        )
        result = await db.execute(q)
        rows = result.scalars().all()

        if not rows:
            return

        # Build conversation text (limit to last 200 msgs to avoid token overflow)
        recent = rows[-200:]
        convo_text = "\n".join([
            f"{r.role.upper()}: {r.content[:300]}" for r in recent
        ])

        llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            api_key=settings.OPENAI_API_KEY,
        )

        summary_prompt = """Você é um sistema de extração de memória qualitativa.
Analise a conversa completa abaixo entre um assistente e um usuário.
Extraia fatos qualitativos, comportamentais, temporais e demográficos RELEVANTES sobre o usuário.

Exemplos:
- "Mora com 4 pessoas na casa"
- "Trabalha no período da noite"
- "Tem interesse no cristianismo e vontade de se batizar"
- "Fez um pedido de oração pela família em março/2026"
- "Costuma responder de madrugada"

Liste os fatos como frases curtas e objetivas, um por linha, sem marcadores.
Se não houver fatos relevantes, responda EXATAMENTE: NENHUM"""

        response = await llm.ainvoke([
            SystemMessage(content=summary_prompt),
            HumanMessage(content=f"Conversa:\n{convo_text}")
        ])

        extracted = response.content.strip()
        if extracted.upper() == "NENHUM" or not extracted:
            print(f"[MTM→LTM] No facts extracted for {session_id}")
            return

        facts = [f.strip("- ") for f in extracted.split("\n") if f.strip() and f.strip().upper() != "NENHUM"]

        if facts:
            weaviate_cli = get_weaviate()
            for fact in facts:
                await weaviate_cli.save_contact_memory(
                    agent_id=str(agent_id),
                    contact_id=str(session_id),
                    content=fact,
                )
            print(f"[MTM→LTM] ✅ Saved {len(facts)} auto-summarized facts for session {session_id}")

    except Exception as e:
        print(f"[MTM→LTM] ❌ Error auto-summarizing: {e}")


# ─────────────────────────────────────────────────────────────
# Collaborator Tools (v0.0.9) — collaborators become tools
# ─────────────────────────────────────────────────────────────

async def _build_collaborator_tools(
    db,
    agent_model,
    message: str,
    context_data: Optional[Dict[str, Any]] = None,
) -> list:
    """
    Build LangChain tools from an orchestrator's collaborators.
    
    Each collaborator agent becomes a callable tool that the orchestrator
    can invoke via its ReAct loop. This keeps everything inside one
    LangGraph execution — no external evaluate/delegate/synthesize.
    
    Returns a list of StructuredTool objects.
    """
    from langchain_core.tools import StructuredTool
    from app.orchestrator.agent_orchestrator import AgentOrchestrator
    from app.models.agent import CollaborationStatus
    import re

    orchestrator = AgentOrchestrator(db)
    agent_with_settings = await orchestrator.get_agent_with_collaborators(agent_model.id)
    if not agent_with_settings or not agent_with_settings.collaborator_settings:
        return []

    enabled = []
    neutral = []
    for setting in agent_with_settings.collaborator_settings:
        if setting.status == CollaborationStatus.ENABLED:
            enabled.append(setting.collaborator)
        elif setting.status == CollaborationStatus.NEUTRAL:
            neutral.append(setting.collaborator)
    all_collaborators = enabled + neutral
    if not all_collaborators:
        return []

    tools = []
    for collab in all_collaborators:
        # Sanitize name for tool compatibility
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', collab.name or "agent")
        safe_name = re.sub(r'^[^a-zA-Z_]', '_', safe_name)
        safe_name = re.sub(r'_+', '_', safe_name).strip('_')[:64]
        tool_name = f"consultar_{safe_name}"

        # Build description with full Capability Map
        base_desc = collab.description or "Especialista"
        details = []
        
        # Capability Map (Skills + Intents)
        if hasattr(collab, 'skills') and collab.skills:
            from app.schemas.skill import get_skill_capability_description
            active_skills = [s for s in collab.skills if s.is_active]
            if active_skills:
                skills_text = ", ".join([
                    f"{s.name}: {get_skill_capability_description(s)}"
                    for s in active_skills
                ])
                details.append(f"CAPACIDADES: {skills_text}")
        
        # Tool Map (MCPs)
        if hasattr(collab, 'mcps') and collab.mcps:
            tool_names = [m.name for m in collab.mcps]
            if tool_names:
                details.append(f"FERRAMENTAS: {', '.join(tool_names)}")
        
        priority = "PRIORITÁRIO" if collab in enabled else "disponível"
        details_str = " | ".join(details) if details else ""
        tool_desc = f"Consulta o agente '{collab.name}' ({priority}). {base_desc}. {details_str}. Envie uma instrução clara do que este agente deve fazer."
        
        # Keep a reasonable limit but much larger than 200 to allow the contract to be seen
        if len(tool_desc) > 1000:
            tool_desc = tool_desc[:997] + "..."

        # Create the tool executor (closure captures collab)
        _collab = collab
        _db = db
        _context_data = context_data

        async def _invoke_collab(instrucao: str, _agent=_collab, _database=_db, _ctx=_context_data) -> str:
            """
            Invoke a collaborator agent with the given instruction.
            Args:
                instrucao: Clear instruction of what this specialist agent should do
            """
            try:
                orch = AgentOrchestrator(_database)
                name, response = await orch._invoke_collaborator(
                    agent=_agent,
                    message=instrucao,
                    history=[],
                    context="",
                    context_data=_ctx,
                    orientation=instrucao,
                )
                print(f"[CollabTool] ✅ '{name}' responded to orchestrator")
                return response or f"Agente {name} não retornou resposta."
            except Exception as e:
                print(f"[CollabTool] ❌ Error invoking '{_agent.name}': {e}")
                return f"Erro ao consultar agente {_agent.name}: {str(e)}"

        tool = StructuredTool.from_function(
            coroutine=_invoke_collab,
            name=tool_name,
            description=tool_desc,
            return_direct=False
        )
        tools.append(tool)
        print(f"[Task] 🔧 Collaborator tool created: {tool_name} → '{collab.name}'")

    return tools


# ─────────────────────────────────────────────────────────────
# Main task: process_message_task
# ─────────────────────────────────────────────────────────────

async def process_message_task(
    ctx: dict,
    message: str,
    session_id: str,
    agent_id: Optional[str] = None,
    user_access_level: str = "normal",
    context_data: Optional[Dict[str, Any]] = None,
    transition_data: Optional[Dict[str, Any]] = None,
    callback_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Background task: process a message.
    
    v0.0.7 Agent-First flow:
      - If agent_id is provided, execute that agent directly (no Supervisor routing)
      - If agent has output_schema, use structured output
      - If is_orchestrator, pre-consult collaborators
      - Supervisor (run_orchestrator_v2) only used as fallback when no agent_id
    """
    start_time = time.time()

    try:
        async with AsyncSessionLocal() as db:
            from app.orchestrator.agent_factory import AgentFactory
            from langchain_core.messages import HumanMessage, AIMessage

            factory = AgentFactory(db)

            # ── Resolve agent ──
            agent = None
            agent_config = None
            if agent_id:
                agent = await factory.get_agent_by_id(agent_id)
                if agent:
                    agent_config = await factory.get_agent_config(agent, context_data=context_data)
            
            if not agent_config:
                # No specific agent → fallback to Supervisor router
                from app.orchestrator import run_orchestrator_v2

                # STM: get history
                history = await redis_client.get_conversation(session_id)
                await redis_client.add_message(
                    session_id=session_id, role="user", content=message, ttl_seconds=86400
                )

                # MTM: fallback logic for fallback path (using nil uuid for agent_id if no agent was resolved)
                import uuid
                fallback_agent_id = str(uuid.UUID(int=0))

                # MTM: save user message
                await _save_mtm_message(db, fallback_agent_id, session_id, "user", message)

                result = await run_orchestrator_v2(
                    message=message,
                    session_id=session_id,
                    history=history,
                    agent_id=None,
                    db=db,
                    user_access_level=user_access_level,
                    context_data=context_data,
                )
                final_result = result["response"]
                agent_used = result.get("agent_used")

                await redis_client.add_message(
                    session_id=session_id, role="assistant",
                    content=str(final_result), ttl_seconds=86400
                )
                
                # MTM: save assistant response
                await _save_mtm_message(db, fallback_agent_id, session_id, "assistant", str(final_result))

                processing_time = (time.time() - start_time) * 1000
                response_data = {
                    "status": "completed",
                    "response": final_result,
                    "agent_used": agent_used,
                    "processing_time_ms": processing_time,
                }
                if transition_data:
                    response_data["transition_data"] = transition_data
                if callback_url:
                    await _send_callback(callback_url, response_data)
                return response_data

            # ── agent_id provided: execute directly ──
            stm_enabled, stm_ttl_seconds = _resolve_stm_config(agent_config)

            # STM: load history
            history = []
            mtm_context_note = ""
            if stm_enabled:
                history = await redis_client.get_conversation(session_id)
                await redis_client.add_message(
                    session_id=session_id, role="user",
                    content=message, ttl_seconds=stm_ttl_seconds
                )

            # MTM fallback: if no STM history, check PostgreSQL
            if not history and agent_id and session_id:
                mtm_history = await _load_mtm_fallback(db, agent_id, session_id, limit=5)
                if mtm_history:
                    history = mtm_history
                    mtm_context_note = (
                        "\n\n## Contexto de Conversa Anterior\n\n"
                        "O usuário já interagiu com você anteriormente. "
                        "As mensagens abaixo são de uma conversa passada (recuperadas da memória de médio prazo). "
                        "Use este contexto para manter a continuidade do atendimento.\n"
                    )
                    print(f"[MTM] 📋 Loaded {len(mtm_history)} messages from MTM for session {session_id}")
                else:
                    has_any = await _check_mtm_has_history(db, agent_id, session_id)
                    if not has_any:
                        mtm_context_note = (
                            "\n\n## Primeiro Contato\n\n"
                            "Este é o primeiro contato deste usuário. Não há histórico de conversas anteriores.\n"
                        )
                        print(f"[MTM] 🆕 First contact for session {session_id}")

            # MTM: save user message to PostgreSQL
            if agent_id and session_id:
                await _save_mtm_message(db, agent_id, session_id, "user", message)

            # Build LangChain messages
            messages = []
            for msg in history:
                timestamp = msg.get("created_at") or msg.get("timestamp")
                prefix = f"[{timestamp}] " if timestamp else ""
                
                if msg.get("role") == "user":
                    messages.append(HumanMessage(content=f"{prefix}{msg['content']}"))
                elif msg.get("role") == "assistant":
                    messages.append(AIMessage(content=f"{prefix}{msg['content']}"))
            messages.append(HumanMessage(content=message))

            # Inject MTM context note into system prompt
            if mtm_context_note:
                agent_config["system_prompt"] = agent_config.get("system_prompt", "") + mtm_context_note

            # Save original system prompt before enrichment (for self-correction analysis)
            agent_config["original_system_prompt"] = agent_config.get("system_prompt", "")

            # Enrich prompt (RAG, InfoBases, VectorMemory, Orchestrator pre-consultation)
            rag_context = await _enrich_agent_prompt(
                db, agent_config, agent_id, message, session_id, context_data, history, transition_data
            )

            # ── Execute agent ──
            if agent_config.get("output_schema"):
                # Structured output
                result_dict = await factory.invoke_agent_structured(
                    agent_config=agent_config,
                    messages=messages,
                    rag_context=rag_context,
                    context_data=context_data,
                )
                print(f"[Task] Structured result: {result_dict}")
                final_result = result_dict if isinstance(result_dict, dict) else {"output": str(result_dict)}
                agent_used = agent_config["name"]

                # Store response
                output_text = final_result.get("output", str(final_result))
                if stm_enabled:
                    await redis_client.add_message(
                        session_id=session_id, role="assistant",
                        content=output_text, ttl_seconds=stm_ttl_seconds
                    )
                # MTM: save assistant response
                if agent_id and session_id:
                    await _save_mtm_message(db, agent_id, session_id, "assistant", output_text)

                processing_time = (time.time() - start_time) * 1000
                response_data = {
                    "status": "completed",
                    **final_result,
                    "agent_used": agent_used,
                    "processing_time_ms": processing_time,
                }
            else:
                # Standard text output
                response = await factory.invoke_agent(
                    agent_config=agent_config,
                    messages=messages,
                    rag_context=rag_context,
                    context_data=context_data,
                )
                print(f"[Task] ✅ {agent_config['name']} responded directly")
                final_result = response
                agent_used = agent_config["name"]


                if stm_enabled:
                    await redis_client.add_message(
                        session_id=session_id, role="assistant",
                        content=str(final_result), ttl_seconds=stm_ttl_seconds
                    )
                # MTM: save assistant response
                if agent_id and session_id:
                    await _save_mtm_message(db, agent_id, session_id, "assistant", str(final_result))

                processing_time = (time.time() - start_time) * 1000
                response_data = {
                    "status": "completed",
                    "response": final_result,
                    "agent_used": agent_used,
                    "processing_time_ms": processing_time,
                }

            if transition_data:
                response_data["transition_data"] = transition_data
            if callback_url:
                await _send_callback(callback_url, response_data)

            # Agent self-correction: detect prompt violations in background
            if vector_memory_enabled and agent_id and final_result:
                try:
                    from app.services.vector_memory_service import extract_agent_self_corrections
                    import asyncio
                    agent_response_str = str(final_result) if not isinstance(final_result, str) else final_result
                    original_system_prompt = agent_config.get("original_system_prompt", agent_config.get("system_prompt", ""))
                    asyncio.create_task(
                        extract_agent_self_corrections(
                            agent_id=str(agent_id),
                            system_prompt=original_system_prompt,
                            agent_response=agent_response_str,
                            user_message=message,
                            history=(history or [])[:],
                        )
                    )
                except Exception as e:
                    print(f"[Task] Failed to launch self-correction task: {e}")

            return response_data

    except Exception as e:
        import traceback
        traceback.print_exc()
        processing_time = (time.time() - start_time) * 1000
        return {
            "status": "failed",
            "response": f"Error processing message: {str(e)}",
            "error": str(e),
            "processing_time_ms": processing_time,
        }


# ─────────────────────────────────────────────────────────────
# Structured task (kept for backward compatibility of enqueue calls)
# ─────────────────────────────────────────────────────────────

async def process_message_structured_task(
    ctx: dict,
    message: str,
    session_id: str,
    agent_id: Optional[str] = None,
    user_access_level: str = "normal",
    context_data: Optional[Dict[str, Any]] = None,
    transition_data: Optional[Dict[str, Any]] = None,
    callback_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Background task: process a message and return structured JSON output.
    In v0.0.7 this delegates to the unified process_message_task which
    auto-detects output_schema.
    """
    return await process_message_task(
        ctx=ctx,
        message=message,
        session_id=session_id,
        agent_id=agent_id,
        user_access_level=user_access_level,
        context_data=context_data,
        transition_data=transition_data,
        callback_url=callback_url,
    )


# ─────────────────────────────────────────────────────────────
# Callback helper
# ─────────────────────────────────────────────────────────────

async def _send_callback(callback_url: str, data: dict):
    """Send callback to external URL."""
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(callback_url, json=data, timeout=10.0)
    except Exception as cb_err:
        print(f"Failed to send callback to {callback_url}: {cb_err}")
