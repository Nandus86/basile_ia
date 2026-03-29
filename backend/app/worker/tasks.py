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
from app.worker.status_monitor import StatusMonitor


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
    history: Optional[List] = None,
    transition_data: Optional[Dict[str, Any]] = None,
    monitor: Optional[StatusMonitor] = None,
    session_context: Optional[Dict[str, Any]] = None,
    user_access_level: str = "normal",
    has_ib_tools: bool = False,
    history_source: str = "NONE",
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
    
    # [12H WINDOW RULE] Calculate deterministic greeting rule in code
    is_within_12h = False
    last_interaction_info = "Nenhuma encontrada no histórico recente."
    
    if history:
        try:
            # Get the very last message from history to check timing
            last_msg = history[-1]
            last_ts = last_msg.get("created_at") or last_msg.get("timestamp")
            
            if last_ts:
                from datetime import datetime as dt_obj
                # Handle both datetime objects and ISO strings safely
                if isinstance(last_ts, str):
                    try:
                        # standard ISO format handling
                        last_dt = dt_obj.fromisoformat(last_ts.replace('Z', '+00:00'))
                    except ValueError:
                        last_dt = None
                elif isinstance(last_ts, dt_obj):
                    last_dt = last_ts
                else:
                    last_dt = None
                
                if last_dt:
                    # Sync timezones for comparison
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=user_tz)
                    else:
                        last_dt = last_dt.astimezone(user_tz)
                    
                    diff_seconds = (now - last_dt).total_seconds()
                    # Rule: if less than 12 hours since last interaction
                    if 0 < diff_seconds < (12 * 3600):
                        is_within_12h = True
                    
                    last_interaction_info = f"{last_dt.strftime('%d/%m/%Y %H:%M:%S')} (há {int(diff_seconds // 3600)}h e {int((diff_seconds % 3600) // 60)}min)"
        except Exception as e:
            print(f"[Task] Error calculating 12h window: {e}")

    # Define explicit greeting instruction for the AI
    if is_within_12h:
        greeting_rule = "🚨 REGRA CRÍTICA DE SAUDAÇÃO: ÚLTIMA INTERAÇÃO HÁ MENOS DE 12H. **NÃO SAUDE O USUÁRIO**. Vá direto ao ponto, sem 'Paz do Senhor', 'Olá', 'Tudo bem?' ou 'Como posso ajudar?'."
    else:
        greeting_rule = "Pode saudar o usuário normalmente (Primeiro contato ou última interação há mais de 12h)."

    agent_config["system_prompt"] = agent_config.get("system_prompt", "") + (
        f"\n\n## Data e Hora Local do Sistema\n"
        f"Abaixo estão os dados temporais deste exato momento. "
        f"Use isso para calcular prazos, responder se é dia/noite ou comparar com "
        f"as datas gravadas nas memórias (que também possuem timestamp).\n"
        f"- Data/Hora legível: {current_time_str}\n"
        f"- Timestamp ISO: {current_iso}\n"
        f"- Última interação detectada: {last_interaction_info}\n"
        f"- **DIRETRIZ DE SAUDAÇÃO**: {greeting_rule}\n"
    )

    # 0. Session Continuity — inject previous agent info
    if session_context:
        last_name = session_context.get("last_agent_name", "")
        agents_used = session_context.get("agents_used", [])
        if last_name:
            agent_config["system_prompt"] = agent_config.get("system_prompt", "") + (
                f"\n\n## Continuidade do Atendimento\n\n"
                f"Este contato foi atendido anteriormente pelo agente \"{last_name}\".\n"
                f"Agentes que já participaram desta sessão: {', '.join(agents_used)}.\n"
                f"Considere este histórico para manter a fluidez do atendimento.\n"
            )
            print(f"[Task] 📋 Session continuity injected: last_agent='{last_name}'")

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

    # 2. Information Bases (skip if agent has IB tools — agent will search on demand)
    if not has_ib_tools:
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
                                    clean_target = target_key.strip()
                                    if clean_target.startswith("$request."):
                                        clean_target = clean_target[len("$request."):]
                                    parts = clean_target.split(".")
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
                            ib_limit = getattr(ib, 'max_results', 3) or 3
                            for uid in possible_ids:
                                info_nodes = await weaviate_cl.search_information_bases(
                                    base_codes=[ib.code], user_id=uid, query=message, limit=ib_limit
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
                                [f"- {n['content']} (Meta: {n['metadata']})" for n in unique_nodes[:6]]
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

                # 3d. Entity-level memories (dynamic entity training)
                agent_model_obj = agent_config.get("agent_model")
                entity_path = getattr(agent_model_obj, "entity_memory_path", None) if agent_model_obj else None
                if entity_path and context_data:
                    # Resolve entity_id from context_data using dot-path
                    def _resolve_path(data, path):
                        clean = path.strip()
                        if clean.startswith("$request."):
                            clean = clean[len("$request."):]
                        parts = clean.split(".")
                        current = data
                        for part in parts:
                            if isinstance(current, dict) and part in current:
                                current = current[part]
                            else:
                                return None
                        return str(current) if current is not None else None
                    
                    entity_id = _resolve_path(context_data, entity_path)
                    if entity_id:
                        entity_memories = await weaviate_client.search_contact_memories(
                            agent_id=str(agent_id),
                            contact_id=entity_id,
                            query=message,
                            limit=5,
                            memory_type="entity_rule"
                        )
                        if entity_memories:
                            print(f"[Task] 🏢 Retrieved {len(entity_memories)} entity memories for {entity_path}={entity_id}")
                            ent_lines = [f"- {m['content']}" for m in entity_memories]
                            ent_str = "\n".join(ent_lines)
                            agent_config["system_prompt"] = agent_config.get("system_prompt", "") + (
                                f"\n\n## 🏢 Regras Específicas da Entidade ({entity_path}={entity_id})\n\n"
                                f"As regras abaixo foram treinadas especificamente para esta entidade. "
                                f"Respeite-as SEMPRE:\n\n"
                                f"{ent_str}\n"
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
            collab_tools, mandatory_instructions = await _build_collaborator_tools(
                db, agent_model, message, context_data, user_access_level=user_access_level
            )
            if collab_tools:
                existing_tools = agent_config.get("tools", []) or []
                agent_config["tools"] = existing_tools + collab_tools
                agent_config["has_tools"] = True
                print(f"[Task] 🎭 Added {len(collab_tools)} collaborator tools to '{agent_config['name']}'")
                
                # Add orchestration instructions to system prompt
                collab_names = [t.name for t in collab_tools]
                
                mandatory_str = ""
                if mandatory_instructions:
                    mandatory_str = "\n\n⚠️ ROTEAMENTO OBRIGATÓRIO POR PALAVRA-CHAVE:\n" + "\n".join(mandatory_instructions)
                    print(f"[Task] 🚨 Injected {len(mandatory_instructions)} mandatory routing instructions for keywords")
                
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
                    f"{mandatory_str}"
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

            orchestrator = AgentOrchestrator(db, monitor=monitor)
            subordinate_context = await orchestrator.gather_subordinate_responses(
                message=message,
                primary_agent=agent_model,
                context=rag_context or "",
                context_data=context_data,
                history=history,
                session_id=session_id,
                monitor=monitor,
                user_access_level=user_access_level,
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
    # 5. [GREETING LOGIC] Replace placeholders and inject state rules
    greeting_config = agent_config.get("greeting_config", {"initial": "", "normal": ""})
    initial_text = greeting_config.get("initial", "")
    normal_text = greeting_config.get("normal", "")

    # Replace placeholders in the system prompt
    current_prompt = agent_config.get("system_prompt", "")
    current_prompt = current_prompt.replace("{{ $greeting.initial }}", initial_text)
    current_prompt = current_prompt.replace("{{ $greeting.normal }}", normal_text)

    # Inject definitive state rule
    state_instruction = ""
    if history_source == "STM":
        state_instruction = (
            "\n\n## ESTADO DA CONVERSA: RECENTE (Fluxo Contínuo)\n"
            "Interação detectada na memória de curto prazo (Redis). "
            "REGRA ABSOLUTA: **NÃO USE SAUDAÇÕES**. Não utilize 'Paz do Senhor', 'Olá', 'Tudo bem?' ou qualquer cumprimento inicial. "
            "A conversa já está em andamento. Responda diretamente ao que foi solicitado.\n"
        )
    elif history_source == "MTM":
        state_instruction = (
            "\n\n## ESTADO DA CONVERSA: RETORNO (Boas-vindas de Volta)\n"
            "O usuário está retornando após algum tempo. "
            f"Se for apropriado saudar, utilize preferencialmente a saudação de retorno: \"{normal_text}\".\n"
        )
    else:
        state_instruction = (
            "\n\n## ESTADO DA CONVERSA: INICIAL (Primeiro Contato)\n"
            "Este é o primeiro contato deste usuário. "
            f"Inicie o atendimento utilizando a saudação inicial: \"{initial_text}\".\n"
        )
    
    agent_config["system_prompt"] = current_prompt + state_instruction

    print(f"[Task] 📝 Greeting logic applied: state={history_source}")

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
    user_access_level: str = "normal",
) -> tuple[list, list]:
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
        return [], []

    # [VERTICAL HIERARCHY] Filter collaborators by user access level
    from app.models.agent import AccessLevel
    try:
        user_level = AccessLevel(user_access_level)
    except ValueError:
        user_level = AccessLevel.NORMAL

    all_collaborators = [
        c for c in all_collaborators
        if user_level.can_access(c.access_level)
    ]

    if not all_collaborators:
        return []

    tools = []
    mandatory_instructions = []

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
        
        priority = "PRIORITÁRIO (RECOMENDADO)" if collab in enabled else "disponível (secundário)"
        
        # KEYWORD MATCHING
        agent_kws = getattr(collab, 'trigger_keywords', []) or []
        msg_lower = message.lower()
        matched_kw = None
        for kw in agent_kws:
            if kw and kw.lower() in msg_lower:
                matched_kw = kw
                break
                
        if matched_kw:
            priority = f"PRIORITÁRIO OBRIGATÓRIO (Keyword: {matched_kw})"
            forced_instr = f"A mensagem do usuário contém a palavra-chave '{matched_kw}' associada ao agente '{collab.name}'. → Você DEVE chamar '{tool_name}' IMEDIATAMENTE."
            
            # Check MCP Keywords on this matched agent
            if hasattr(collab, 'mcps') and collab.mcps:
                for mcp in collab.mcps:
                    mcp_kws = getattr(mcp, 'trigger_keywords', []) or []
                    for mkw in mcp_kws:
                        if mkw and mkw.lower() in msg_lower:
                            # Usually MCP tool is `execute_{safe_name_of_mcp}` but we don't know the exact python function name here, 
                            # we can just refer to the tool name from the orchestrator perspective. "execute_NOME"
                            mcp_safe = re.sub(r'[^a-zA-Z0-9_-]', '_', mcp.name)
                            forced_instr += f"\n→ Ocasionalmente, ele DEVE usar a ferramenta 'execute_{mcp_safe}' ({mcp.name}) antes de qualquer outra ação."
                            break
            mandatory_instructions.append(forced_instr)
            
        details_str = " | ".join(details) if details else ""
        tool_desc = f"Consulta o agente especialista '{collab.name}' [{priority}]. {base_desc}. {details_str}. Envie uma instrução clara e técnica do que este agente deve fazer especificamente."
        
        # Keep a reasonable limit but much larger than 200 to allow the contract to be seen
        if len(tool_desc) > 1000:
            tool_desc = tool_desc[:997] + "..."

        # Create the tool executor (closure captures collab)
        _collab = collab
        _db = db
        _context_data = context_data
        _is_planner = getattr(collab, "is_planner", False)
        _planner_prompt = getattr(collab, "planner_prompt", None)
        _planner_model = getattr(collab, "planner_model", None)

        async def _invoke_collab(instrucao: str, _agent=_collab, _database=_db, _ctx=_context_data, _planner_enabled=_is_planner, _p_prompt=_planner_prompt, _p_model=_planner_model) -> str:
            """
            Invoke a collaborator agent with the given instruction.
            Args:
                instrucao: Clear instruction of what this specialist agent should do
            """
            try:
                orch = AgentOrchestrator(_database)
                
                final_instruction = instrucao
                
                if _planner_enabled:
                    try:
                        from langchain_openai import ChatOpenAI
                        from langchain_core.messages import SystemMessage, HumanMessage
                        from app.config import settings
                        import json
                        
                        planner_llm = ChatOpenAI(
                            model=_p_model or "gpt-4o-mini",
                            temperature=0.7,
                            api_key=settings.OPENAI_API_KEY
                        )
                        
                        planner_prompt = _p_prompt or (
                            "Você é o Planejador Mestre do Orquestrador. "
                            "Sua função é pegar uma instrução e quebrá-la em um checklist de passos granulares (Tasks) "
                            "para outro agente técnico executar. O agente que receberá isto só terminará o trabalho quando finalizar todas as tarefas. "
                            "Responda APENAS com o texto a ser enviado, incluindo o checklist em formato Markdown '- [ ] Nome da tarefa'."
                        )
                        
                        planner_resp = await planner_llm.ainvoke([
                            SystemMessage(content=planner_prompt),
                            HumanMessage(content=f"Crie as tasks para a seguinte instrução:\n{instrucao}")
                        ])
                        
                        tasks_str = planner_resp.content
                        final_instruction = f"INSTRUÇÃO ORIGINAL:\n{instrucao}\n\nO ORQUESTRADOR DEFINIU AS SEGUINTES TAREFAS (RESOLVA-AS E RESPONDA COM O RESULTADO):\n{tasks_str}"
                        print(f"[CollabTool] 📋 Planner gerou tasks para '{_agent.name}'")
                    except Exception as planner_err:
                        print(f"[CollabTool] ⚠️ Erro no Planner LLM, enviando instrução original. Erro: {planner_err}")

                name, response = await orch._invoke_collaborator(
                    agent=_agent,
                    message=final_instruction,
                    history=[],
                    context="",
                    context_data=_ctx,
                    orientation=final_instruction,
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

    return tools, mandatory_instructions


# ─────────────────────────────────────────────────────────────
# Information Base Tools — one native tool per information base
# ─────────────────────────────────────────────────────────────

async def _build_information_base_tools(
    db,
    agent_id: str,
    context_data: Optional[Dict[str, Any]] = None,
) -> list:
    """
    Build one StructuredTool per active Information Base associated with the agent.
    Each tool searches Weaviate using the base's own correlation_schema to resolve user_id.
    """
    from langchain_core.tools import StructuredTool
    from app.models.agent import Agent as AgentModel
    from sqlalchemy import select as sa_select
    from sqlalchemy.orm import selectinload
    from app.weaviate_client import get_weaviate

    result = await db.execute(
        sa_select(AgentModel)
        .options(selectinload(AgentModel.information_bases))
        .where(AgentModel.id == agent_id)
    )
    agent_obj = result.scalar_one_or_none()
    if not agent_obj or not agent_obj.information_bases:
        return []

    active_bases = [b for b in agent_obj.information_bases if b.is_active]
    if not active_bases:
        return []

    weaviate_cl = get_weaviate()
    if not weaviate_cl:
        print(f"[Task] ⚠️ Weaviate client not available, skipping information base tools")
        return []

    tools = []
    ctx = context_data or {}

    for ib in active_bases:
        # Resolve user_id from context_data via correlation_schema
        user_id = None
        if ib.correlation_schema and isinstance(ib.correlation_schema, dict):
            target_key = ib.correlation_schema.get("target")
            if target_key:
                clean_target = target_key.strip()
                if clean_target.startswith("$request."):
                    clean_target = clean_target[len("$request."):]
                parts = clean_target.split(".")
                val = ctx
                for part in parts:
                    if isinstance(val, dict) and part in val:
                        val = val[part]
                    else:
                        val = None
                        break
                if val is not None and not isinstance(val, (dict, list)):
                    user_id = str(val).strip() or None

        if not user_id:
            # Fallback: use first string value from context_data
            for k, v in ctx.items():
                if isinstance(v, str) and v.strip():
                    user_id = v.strip()
                    break

        if not user_id:
            print(f"[Task] ⚠️ Could not resolve user_id for base '{ib.name}', skipping tool creation")
            continue

        # Sanitize base code for tool name
        import re
        safe_code = re.sub(r'[^a-zA-Z0-9_]', '_', ib.code or ib.name or "base")
        safe_code = re.sub(r'^[^a-zA-Z_]', '_', safe_code)
        safe_code = re.sub(r'_+', '_', safe_code).strip('_')[:64]
        tool_name = f"pesquisar_{safe_code.lower()}"

        _base_code = ib.code
        _base_name = ib.name
        _uid = user_id
        _wc = weaviate_cl
        _max = getattr(ib, 'max_results', 3) or 3

        async def _search_base(query: str, _bc=_base_code, _bn=_base_name, _u=_uid, _w=_wc, _m=_max) -> str:
            """Search this information base for relevant content."""
            try:
                results = await _w.search_information_bases(
                    base_codes=[_bc],
                    user_id=_u,
                    query=query,
                    limit=_m,
                )
                if not results:
                    return f"Nenhum resultado encontrado na base '{_bn}'."
                lines = [f"- {r['content']}" for r in results]
                return f"Resultados da base '{_bn}':\n" + "\n".join(lines)
            except Exception as e:
                return f"Erro ao pesquisar base '{_bn}': {str(e)}"

        tool_desc = (
            f"Pesquisa na base de informação '{ib.name}'. "
            f"Use esta ferramenta UMA VEZ para buscar informações relevantes. "
            f"Descreva claramente o que deseja encontrar. NÃO repita a mesma busca."
        )

        tool = StructuredTool.from_function(
            coroutine=_search_base,
            name=tool_name,
            description=tool_desc,
            return_direct=False,
        )
        tools.append(tool)
        print(f"[Task] 🔧 Information Base tool created: {tool_name} → '{ib.name}' (user_id={user_id})")

    return tools


# ─────────────────────────────────────────────────────────────
# Global Trigger MCP Pre-execution — check ALL MCPs for trigger_keywords match
# ─────────────────────────────────────────────────────────────

async def _check_global_trigger_keywords(
    db,
    message: str,
    context_data: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Check ALL active MCPs in the system for trigger_keywords matching the message.
    If a match is found, execute the MCP tool directly and return results
    for injection into the agent's system prompt.
    
    This runs BEFORE any agent routing, checking globally across all MCPs.
    """
    from app.services.mcp_tools import MCPToolExecutor
    from app.models.mcp import MCP
    from sqlalchemy import select as sa_select
    import json

    msg_lower = message.lower()

    result = await db.execute(
        sa_select(MCP)
        .where(
            MCP.is_active == True,
            MCP.trigger_keywords.isnot(None),
        )
    )
    all_mcps = result.scalars().all()

    triggered_mcps = []
    for mcp in all_mcps:
        mcp_kws = mcp.trigger_keywords or []
        matched_kw = None
        for kw in mcp_kws:
            if kw and kw.lower().strip() in msg_lower:
                matched_kw = kw
                break
        if matched_kw:
            triggered_mcps.append((mcp, matched_kw))

    if not triggered_mcps:
        return None

    print(f"[GlobalTrigger] 🎯 Found {len(triggered_mcps)} MCP(s) with matching trigger_keywords")

    executor = MCPToolExecutor(db, context_data=context_data)
    results_parts = []

    for mcp, matched_kw in triggered_mcps:
        print(f"[GlobalTrigger] ⚡ Executing MCP '{mcp.name}' triggered by keyword '{matched_kw}'")
        try:
            tools = await executor.create_langchain_tools(mcp)
            if not tools:
                print(f"[GlobalTrigger] ⚠️ No tools discovered for MCP '{mcp.name}'")
                continue

            for tool in tools:
                try:
                    result = await tool.coroutine()
                    try:
                        parsed = json.loads(result)
                        if isinstance(parsed, dict) and "output" in parsed:
                            result = parsed["output"]
                        elif isinstance(parsed, dict) and "result" in parsed:
                            result = parsed["result"]
                    except (json.JSONDecodeError, TypeError):
                        pass
                    results_parts.append(f"### Resultado de '{mcp.name}' (via trigger '{matched_kw}'):\n{result}")
                    print(f"[GlobalTrigger] ✅ MCP '{mcp.name}' executed successfully")
                except Exception as tool_err:
                    print(f"[GlobalTrigger] ❌ Error executing tool '{tool.name}': {tool_err}")
                    results_parts.append(f"### Erro ao executar '{mcp.name}': {tool_err}")
        except Exception as e:
            print(f"[GlobalTrigger] ❌ Error processing MCP '{mcp.name}': {e}")

    if results_parts:
        return (
            "\n\n## ⚡ Dados Pré-Executados via Trigger Global\n\n"
            "Os seguintes MCPs foram ativados automaticamente por palavras-chave na mensagem do usuário. "
            "Use os dados abaixo para compor sua resposta:\n\n"
            + "\n\n".join(results_parts)
            + "\n"
        )

    return None


# ─────────────────────────────────────────────────────────────
# Trigger MCP Pre-execution — force MCP execution when keyword matches
# ─────────────────────────────────────────────────────────────

async def _check_trigger_mcps(
    db,
    agent_id: str,
    message: str,
    context_data: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Check if any MCPs assigned to the agent have trigger_keywords matching the message.
    If match found, execute the MCP tools DIRECTLY (without LLM) and return results
    for injection into the agent's system prompt.
    """
    from app.services.mcp_tools import MCPToolExecutor
    from app.models.agent import Agent as AgentModel
    from app.models.mcp_group import MCPGroup
    from sqlalchemy import select as sa_select
    from sqlalchemy.orm import selectinload
    import json

    # Load agent with MCPs (direct + groups)
    result = await db.execute(
        sa_select(AgentModel)
        .options(
            selectinload(AgentModel.mcps),
            selectinload(AgentModel.mcp_groups).selectinload(MCPGroup.mcps),
        )
        .where(AgentModel.id == agent_id)
    )
    agent_obj = result.scalar_one_or_none()
    if not agent_obj:
        return None

    # Collect all unique MCPs
    all_mcps = []
    seen_ids = set()
    if agent_obj.mcps:
        for mcp in agent_obj.mcps:
            if mcp.is_active and mcp.id not in seen_ids:
                all_mcps.append(mcp)
                seen_ids.add(mcp.id)
    if hasattr(agent_obj, "mcp_groups") and agent_obj.mcp_groups:
        for group in agent_obj.mcp_groups:
            if group.is_active and group.mcps:
                for mcp in group.mcps:
                    if mcp.is_active and mcp.id not in seen_ids:
                        all_mcps.append(mcp)
                        seen_ids.add(mcp.id)

    if not all_mcps:
        return None

    msg_lower = message.lower()
    triggered_mcps = []

    # Check each MCP for keyword match
    for mcp in all_mcps:
        mcp_kws = getattr(mcp, "trigger_keywords", None) or []
        matched_kw = None
        for kw in mcp_kws:
            if kw and kw.lower() in msg_lower:
                matched_kw = kw
                break
        if matched_kw:
            triggered_mcps.append((mcp, matched_kw))

    if not triggered_mcps:
        return None

    # Execute triggered MCP tools directly
    executor = MCPToolExecutor(db, context_data=context_data)
    results_parts = []

    for mcp, matched_kw in triggered_mcps:
        print(f"[Trigger] 🎯 MCP '{mcp.name}' triggered by keyword '{matched_kw}'")
        try:
            tools = await executor.create_langchain_tools(mcp)
            if not tools:
                print(f"[Trigger] ⚠️ No tools discovered for MCP '{mcp.name}'")
                continue

            for tool in tools:
                print(f"[Trigger] ⚡ Executing MCP tool '{tool.name}' directly")
                try:
                    result = await tool.coroutine()
                    # Try to parse and format JSON results
                    try:
                        parsed = json.loads(result)
                        if isinstance(parsed, dict) and "output" in parsed:
                            result = parsed["output"]
                        elif isinstance(parsed, dict) and "result" in parsed:
                            result = parsed["result"]
                    except (json.JSONDecodeError, TypeError):
                        pass
                    results_parts.append(f"### Resultado de '{mcp.name}' (via trigger '{matched_kw}'):\n{result}")
                    print(f"[Trigger] ✅ MCP '{mcp.name}' executed successfully")
                except Exception as tool_err:
                    print(f"[Trigger] ❌ Error executing tool '{tool.name}': {tool_err}")
                    results_parts.append(f"### Erro ao executar '{mcp.name}': {tool_err}")
        except Exception as e:
            print(f"[Trigger] ❌ Error processing MCP '{mcp.name}': {e}")

    if results_parts:
        return (
            "\n\n## ⚡ Dados Pré-Executados via Trigger\n\n"
            "Os seguintes MCPs foram ativados automaticamente por palavras-chave na mensagem do usuário. "
            "Use os dados abaixo para compor sua resposta:\n\n"
            + "\n\n".join(results_parts)
            + "\n"
        )

    return None


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
    
    # Set request context for deep services (MCP tools)
    from app.context import set_request_context
    set_request_context(context_data or {})

    agent = None
    agent_config = None
    monitor = None

    trigger_results = None

    try:
        async with AsyncSessionLocal() as db:
            from app.orchestrator.agent_factory import AgentFactory
            from langchain_core.messages import HumanMessage, AIMessage

            print("[Task] 🔍 Checking global trigger keywords...")
            try:
                trigger_results = await _check_global_trigger_keywords(db, message, context_data)
                if trigger_results:
                    print("[Task] 🎯 Global trigger MCP results found and ready to inject")
            except Exception as e:
                import traceback
                print(f"[Task] ❌ Error checking global trigger keywords: {e}")
                traceback.print_exc()

            factory = AgentFactory(db)

            # ── Resolve agent ──
            if agent_id:
                agent = await factory.get_agent_by_id(agent_id)
                if agent:
                    agent_config = await factory.get_agent_config(agent, context_data=context_data)
            
            # Job Status Updates Monitor
            if callback_url:
                monitor = StatusMonitor(
                    callback_url=callback_url,
                    agent_config={
                        "status_updates_enabled": getattr(agent, "status_updates_enabled", True) if agent else True,
                        "status_updates_config": getattr(agent, "status_updates_config", {}) if agent else {}
                    },
                    session_id=session_id,
                    start_time=start_time,
                    transition_data=transition_data
                )
                await monitor.start()

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
                    monitor=monitor
                )
                final_result = result["response"]
                agent_used = result.get("agent_used")
                last_agent = result.get("last_agent")

                if "[FIM_DE_INTERACAO]" in str(final_result):
                    final_result = ""
                    print(f"[Task] 🛑 Interação finalizada silenciosamente pelo supervisor")

                if str(final_result).strip():
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
                    "last_agent": last_agent,
                }
                if transition_data:
                    response_data["transition_data"] = transition_data
                if callback_url:
                    await _send_callback(callback_url, response_data)
                return response_data

            # ── agent_id provided: execute directly ──
            stm_enabled, stm_ttl_seconds = _resolve_stm_config(agent_config)
            vector_memory_enabled = getattr(agent_config.get("agent_model"), "vector_memory_enabled", False)

            # STM: load history
            history = []
            history_source = "NONE"
            mtm_context_note = ""
            if stm_enabled:
                history = await redis_client.get_conversation(session_id)
                if history:
                    history_source = "STM"
                
                await redis_client.add_message(
                    session_id=session_id, role="user",
                    content=message, ttl_seconds=stm_ttl_seconds
                )

            # Build context notes based on STM/MTM history
            mtm_context_note = ""
            is_first_interaction = False

            # MTM fallback: if no STM history, check PostgreSQL
            if not history and agent_id and session_id:
                mtm_history = await _load_mtm_fallback(db, agent_id, session_id, limit=5)
                if mtm_history:
                    history = mtm_history
                    history_source = "MTM"
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
                        is_first_interaction = True
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
                prefix = f"[CONTEXTO_TEMPORAL: {timestamp}] " if timestamp else ""
                
                if msg.get("role") == "user":
                    messages.append(HumanMessage(content=f"{prefix}{msg['content']}"))
                elif msg.get("role") == "assistant":
                    messages.append(AIMessage(content=f"{prefix}{msg['content']}"))
            messages.append(HumanMessage(content=message))

            # Inject MTM context note into system prompt
            if mtm_context_note:
                agent_config["system_prompt"] = agent_config.get("system_prompt", "") + mtm_context_note

            # Adicionar regra de encerramento de interação
            agent_config["system_prompt"] = agent_config.get("system_prompt", "") + (
                "\n\n## Regra de Encerramento Subentendido\n"
                "Caso a mensagem atual do usuário seja EXCLUSIVAMENTE um agradecimento final, despedida ou negação de mais ajuda (ex: 'não, era só isso, obrigado', 'tchau', 'valeu'), "
                "e NÃO contenha nenhuma nova solicitação, você DEVE responder EXATAMENTE E APENAS com o código: `[FIM_DE_INTERACAO]`."
            )

            # Reforçar a regra de metadados temporais
            agent_config["system_prompt"] = agent_config.get("system_prompt", "") + (
                "\n\n## Atenção aos Metadados Temporais\n"
                "As mensagens no histórico contêm o prefixo `[CONTEXTO_TEMPORAL: ...]`. "
                "Este prefixo NÃO faz parte do conteúdo da mensagem e NUNCA deve ser incluído na sua resposta."
            )

            # Save original system prompt before enrichment (for self-correction analysis)
            agent_config["original_system_prompt"] = agent_config.get("system_prompt", "")

            # Load session context for continuity
            session_context = None
            try:
                session_context = await redis_client.get_session_context(session_id)
                if session_context:
                    print(f"[Task] 📋 Session context loaded: last_agent='{session_context.get('last_agent_name')}', agents_used={session_context.get('agents_used')}")
            except Exception as e:
                print(f"[Task] ⚠️ Failed to load session context: {e}")

            # [INFORMATION BASE TOOLS] Build IB tools first to know if RAG enrichment should skip
            has_ib_tools = False
            try:
                ib_tools = await _build_information_base_tools(db, agent_id, context_data)
                if ib_tools:
                    existing_tools = agent_config.get("tools", []) or []
                    agent_config["tools"] = existing_tools + ib_tools
                    agent_config["has_tools"] = True
                    has_ib_tools = True
                    print(f"[Task] 🔍 Added {len(ib_tools)} information base tools to '{agent_config['name']}'")
            except Exception as e:
                import traceback
                print(f"[Task] ❌ Error loading information base tools: {e}")
                traceback.print_exc()

            # Enrich prompt (RAG, InfoBases as context if no tools, VectorMemory, Orchestrator, Session Continuity)
            rag_context = await _enrich_agent_prompt(
                db, agent_config, agent_id, message, session_id, context_data, history, transition_data,
                session_context=session_context,
                user_access_level=user_access_level,
                has_ib_tools=has_ib_tools,
                history_source=history_source,
            )

            # [TRIGGER MCPs] Use global trigger results if available, otherwise check local
            try:
                if not trigger_results:
                    trigger_results = await _check_trigger_mcps(db, agent_id, message, context_data)
                if trigger_results:
                    agent_config["system_prompt"] = agent_config.get("system_prompt", "") + trigger_results
                    print(f"[Task] 🎯 Trigger MCP results injected into agent prompt")
            except Exception as e:
                import traceback
                print(f"[Task] ❌ Error checking trigger MCPs: {e}")
                traceback.print_exc()

            # ── Execute agent ──
            resilience_cfg = agent_config.get("resilience", {}) if agent_config else {}
            max_retries = resilience_cfg.get("max_retries", 2)
            timeout_seconds = resilience_cfg.get("timeout_seconds", 120)
            retry_count = 0

            while retry_count <= max_retries:
                try:
                    import asyncio
                    if agent_config.get("output_schema"):
                        # Structured output
                        result_dict = await asyncio.wait_for(
                            factory.invoke_agent_structured(
                                agent_config=agent_config,
                                messages=messages,
                                rag_context=rag_context,
                                context_data=context_data,
                            ),
                            timeout=timeout_seconds
                        )
                        print(f"[Task] Structured result: {result_dict}")
                        final_result = result_dict if isinstance(result_dict, dict) else {"output": str(result_dict)}
                        agent_used = agent_config["name"]
                        output_text = final_result.get("output", str(final_result))
                    else:
                        # Standard text output
                        response = await asyncio.wait_for(
                            factory.invoke_agent(
                                agent_config=agent_config,
                                messages=messages,
                                rag_context=rag_context,
                                context_data=context_data,
                            ),
                            timeout=timeout_seconds
                        )
                        final_result = response
                        agent_used = agent_config["name"]
                        output_text = str(final_result)
                except asyncio.TimeoutError:
                    print(f"[Task] ⏱️ Agent execution timed out after {timeout_seconds}s")
                    raise

                # Interceptar FIM DE INTERACAO
                if "[FIM_DE_INTERACAO]" in output_text:
                    output_text = ""
                    if isinstance(final_result, dict):
                        final_result["output"] = ""
                    else:
                        final_result = ""
                    print(f"[Task] 🛑 Interação finalizada silenciosamente pelo agente {agent_used}")

                # Validação (Guardrail)
                is_guardrail_active = agent_config.get("is_guardrail_active", False)
                if is_guardrail_active and output_text.strip() and ("[FIM_DE_INTERACAO]" not in output_text) and not is_first_interaction:
                    validation_msg = await _validate_response(
                        agent_config.get("system_prompt", ""), 
                        output_text,
                        agent_config.get("guardrail_prompt"),
                        agent_config.get("guardrail_model")
                    )
                    if validation_msg != "VALID" and retry_count < max_retries:
                        print(f"[Task] ⚠️ Validação falhou (tentativa {retry_count+1}/{max_retries}). Motivo: {validation_msg}")
                        messages.append(AIMessage(content=output_text))
                        messages.append(HumanMessage(content=f"ATENÇÃO - REJEITADO PELO VALIDADOR INTERNO: A sua última resposta violou suas regras fundamentais.\nMotivo: {validation_msg}\nPor favor, refaça a resposta corrigindo este erro. Responda apenas com a versão corrigida."))
                        retry_count += 1
                        continue  # Tenta novamente
                    elif validation_msg != "VALID":
                        print(f"[Task] ❌ Limite de tentativas de validação atingido. A resposta defeituosa será enviada assim mesmo.")

                # Se chegou aqui, a resposta é válida, o limite foi atingido, é o primeiro contato, ou é fim de interação
                print(f"[Task] ✅ {agent_used} responded on try {retry_count+1}")
                if output_text.strip():
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
                    "agent_used": agent_used,
                    "processing_time_ms": processing_time,
                }
                
                if isinstance(final_result, dict):
                    response_data.update(final_result)
                else:
                    response_data["response"] = final_result
                    
                break  # Sai do loop while

            if transition_data:
                response_data["transition_data"] = transition_data
            if callback_url:
                await _send_callback(callback_url, response_data)

            # Save session context for continuity
            try:
                await redis_client.save_session_context(
                    session_id=session_id,
                    agent_id=str(agent_id),
                    agent_name=agent_used,
                    ttl_seconds=stm_ttl_seconds,
                )
                response_data["last_agent"] = agent_used
                print(f"[Task] 💾 Session context saved: last_agent='{agent_used}'")
            except Exception as e:
                print(f"[Task] ⚠️ Failed to save session context: {e}")

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
        
        friendly_message = await _invoke_recovery_agent(message, str(e))
        
        # Guardar na memória de curto prazo (STM) se ativado
        try:
            await redis_client.add_message(
                session_id=session_id, role="assistant",
                content=friendly_message, ttl_seconds=86400
            )
        except Exception:
            pass
            
        # Para saídas que esperavam schema estruturado
        is_structured = agent_config and agent_config.get("output_schema") if 'agent_config' in locals() and agent_config else False
        
        if is_structured:
            return {
                "status": "completed",
                "output": friendly_message,
                "error": str(e),
                "agent_used": "Agente de Recuperação",
                "processing_time_ms": processing_time,
            }
        else:
            return {
                "status": "completed",
                "response": friendly_message,
                "error": str(e),
                "agent_used": "Agente de Recuperação",
                "processing_time_ms": processing_time,
            }
    finally:
        # Stop StatusMonitor to prevent resource leaks
        if monitor:
            try:
                await monitor.stop()
            except Exception:
                pass

async def _invoke_recovery_agent(message: str, error_msg: str) -> str:
    """Invokes a recovery agent to provide a friendly response after a timeout/error."""
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage
        from app.config import settings
        
        error_llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.7,
            api_key=settings.OPENAI_API_KEY
        )
        
        error_prompt = (
            "Você é um agente de contingência e recuperação. "
            "Ocorreu um erro técnico (como timeout ou falha de comunicação) "
            "ao tentar processar a solicitação do usuário. "
            "Sua tarefa é criar uma resposta amigável e empática, pedindo desculpas pela interrupção "
            "e sugerindo que o usuário tente novamente, pergunte de outra forma ou continue a conversa. "
            "NUNCA exiba detalhes técnicos do erro ao usuário."
        )
        
        response = await error_llm.ainvoke([
            SystemMessage(content=error_prompt),
            HumanMessage(content=f"A mensagem do usuário foi: '{message}'\n\nPor favor, gere a resposta amigável de recuperação.")
        ])
        
        return response.content
    except Exception as e:
        print(f"[Recovery Agent] Failed: {e}")
        return "Desculpe, tivemos uma instabilidade de conexão inesperada. Você poderia tentar novamente em instantes?"


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

async def _validate_response(system_prompt: str, agent_response: str, guardrail_prompt: Optional[str] = None, guardrail_model: Optional[str] = None) -> str:
    """
    Analyzes if the agent's response violates its system prompt or basic constraints.
    Returns "VALID" if everything is okay, or a description of the violation.
    """
    if not system_prompt or not agent_response:
        return "VALID"

    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage
    from app.config import settings

    llm = ChatOpenAI(
        model=guardrail_model or "gpt-4o-mini",
        temperature=0.0,
        api_key=settings.OPENAI_API_KEY
    )

    check_prompt = guardrail_prompt or """Você é um sistema validador de IA (Guardrail).
Sua função é garantir que a RESPOSTA DO AGENTE não viole as regras estabelecidas no PROMPT DO SISTEMA.

Verifique estritamente:
1. O agente respondeu algo claramente proibido pelo prompt?
2. O agente ignorou uma restrição explícita (ex: "Não cumprimentar", "Apenas formatar JSON", "Não dar conselhos médicos")?

Se a resposta estiver de acordo com as regras ou não contiver erro crítico, responda EXATAMENTE: VALID
Se houver uma violação clara, responda descrevendo o erro e instruindo a correção de forma imperativa.

Seja rigoroso, mas justo. Só invalide se houver QUEBRA DE REGRA CLARA."""

    analysis_input = f"""PROMPT DO SISTEMA (Regras):
---
{system_prompt[:3000]}
---

RESPOSTA GERADA PELO AGENTE:
{agent_response[:2000]}"""

    try:
        response = await llm.ainvoke([
            SystemMessage(content=check_prompt),
            HumanMessage(content=analysis_input)
        ])
        
        extracted = response.content.strip()
        if extracted.upper() == "VALID":
            return "VALID"
        return extracted
    except Exception as e:
        print(f"[Validator] Error during validation: {e}")
        return "VALID"
