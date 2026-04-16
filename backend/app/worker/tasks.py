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
import re
from datetime import datetime
from typing import Optional, Dict, Any, List

from app.database import AsyncSessionLocal
from app.redis_client import redis_client, get_redis
from app.config import settings
from app.worker.status_monitor import StatusMonitor


# ─────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────

def _resolve_template(template: str, context_data: Dict[str, Any]) -> str:
    """Resolve template like {{ $request.ai_params.cell_name }} from context_data."""
    resolved = template
    for match in re.finditer(r'\{\{\s*\$request\.([^}]+)\s*\}\}', template):
        path = match.group(1)
        value = context_data
        for key in path.split('.'):
            value = value.get(key, "") if isinstance(value, dict) else ""
        resolved = resolved.replace(match.group(0), str(value))
    return resolved


def _resolve_tz_name(transition_data: Optional[Dict[str, Any]] = None) -> str:
    """Extract IANA timezone name from transition_data payload.
    Falls back to 'America/Sao_Paulo' if not found."""
    tz_name = 'America/Sao_Paulo'
    if not transition_data:
        return tz_name
    # Direct top-level key
    if isinstance(transition_data.get('zoneName'), str):
        return transition_data['zoneName']
    # Nested: church -> address -> timezone -> zoneName
    church_dict = transition_data.get('church', {})
    if isinstance(church_dict, dict):
        address_dict = church_dict.get('address', {})
        if isinstance(address_dict, dict):
            timezone_dict = address_dict.get('timezone', {})
            if isinstance(timezone_dict, dict):
                zone_val = timezone_dict.get('zoneName')
                if zone_val and isinstance(zone_val, str):
                    return zone_val
    return tz_name

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

    # Resolve dynamically provided timezone from transition_data
    tz_name = _resolve_tz_name(transition_data)

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
                    ib_global_search = getattr(ib_agent, "information_bases_global_search_enabled", False)

                    if weaviate_cl:
                        if ib_global_search:
                            possible_ids = []
                            for ib in active_bases:
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

                            if not possible_ids:
                                for k, v in ctx.items():
                                    if isinstance(v, str) and v.strip():
                                        possible_ids.append(v.strip())
                                if session_id:
                                    possible_ids.append(str(session_id))

                            possible_ids = list(dict.fromkeys(possible_ids))
                            base_codes = [ib.code for ib in active_bases if ib.code]
                            ib_limit = max([getattr(ib, 'max_results', 3) or 3 for ib in active_bases] or [3])
                            for uid in possible_ids:
                                info_nodes = await weaviate_cl.search_information_bases(
                                    base_codes=base_codes, user_id=uid, query=message, limit=ib_limit
                                )
                                if info_nodes:
                                    all_info_nodes.extend(info_nodes)
                        else:
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

                                possible_ids = list(dict.fromkeys(possible_ids))
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
                            unique_nodes = []
                            for n in all_info_nodes:
                                # Deduplicate by metadata (not content) to avoid repeating
                                # the same record from multiple facets (summary + field chunks)
                                meta_key = n.get("metadata", "")
                                if meta_key not in seen:
                                    seen.add(meta_key)
                                    unique_nodes.append(n)

                            print(f"[Task] 📚 Retrieved {len(unique_nodes)} Information Base contexts (from {len(all_info_nodes)} facets)")
                            info_parts = []
                            for n in unique_nodes[:6]:
                                # Use metadata (complete data) for prompt injection
                                meta_str = n.get('metadata', '{}')
                                info_parts.append(f"- {meta_str}")
                            info_str = "\n".join(info_parts)
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

        # Extract new vector memories in background (only if interaction is substantive)
        try:
            from app.services.memory_gate import should_extract_memories
            if should_extract_memories(message, history=history):
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
            collab_tools, mandatory_instructions, deterministic_matches = await _build_collaborator_tools(
                db, agent_model, message, context_data, user_access_level=user_access_level
            )

            if deterministic_matches:
                from app.orchestrator.agent_orchestrator import AgentOrchestrator

                selected_match = deterministic_matches[0]
                selected_collab = selected_match["agent"]
                selected_keyword = selected_match["keyword"]
                selected_mode = selected_match["mode"]

                direct_orchestrator = AgentOrchestrator(db, monitor=monitor)
                orientation = (
                    f"TRUE_TRIGGER_KEYWORD acionado ({selected_mode}: '{selected_keyword}'). "
                    f"Executar atendimento completo desta solicitação com máxima prioridade: {message}"
                )
                collab_name, collab_response = await direct_orchestrator._invoke_collaborator(
                    agent=selected_collab,
                    message=message,
                    history=history or [],
                    context=rag_context or "",
                    context_data=context_data,
                    orientation=orientation,
                    primary_agent=agent_model,
                    monitor=monitor,
                    response_style=getattr(selected_collab, "response_style", "structured"),
                )

                if collab_response:
                    filtered_tools = []
                    for tool in collab_tools:
                        tname = getattr(tool, "name", "")
                        if tname and collab_name and tname.lower().endswith((collab_name or "").lower().replace(" ", "_")):
                            continue
                        filtered_tools.append(tool)
                    if len(filtered_tools) != len(collab_tools):
                        collab_tools = filtered_tools

                    agent_config["system_prompt"] = agent_config.get("system_prompt", "") + (
                        f"\n\n## TRUE TRIGGER EXECUTADO (DETERMINÍSTICO)\n"
                        f"- Agente acionado diretamente: {collab_name}\n"
                        f"- Modo de match: {selected_mode}\n"
                        f"- Keyword: {selected_keyword}\n"
                        f"- Resultado bruto:\n{collab_response}\n"
                        f"Use este resultado como fonte prioritária e não reacione o mesmo especialista para a mesma tarefa neste turno.\n"
                    )
                    print(f"[Task] ✅ True trigger executado: '{collab_name}' via keyword '{selected_keyword}' ({selected_mode})")

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
                    f"3. ADAPTAÇÃO: Após obter respostas dos especialistas, avalie se é necessário adaptar ou sintetizar. "
                    f"Se UM especialista retornou uma resposta clara e completa, utilize-a diretamente com pequenas adaptações de tom. "
                    f"Se MÚLTIPLOS especialistas contribuíram, sintetize as informações em uma resposta coesa. "
                    f"NUNCA simplesmente copie respostas que pareçam relatórios técnicos internos.\n"
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
                    f"Os seguintes especialistas forneceram contribuições sobre a solicitação do usuário. "
                    f"Se as respostas já estiverem adequadas para o usuário final, utilize-as diretamente. "
                    f"Se necessário, sintetize e adapte o conteúdo para garantir clareza e coesão:\n"
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

    # Resolve global macros like {{ $now }} with ISO-8601 format
    try:
        from app.utils.macros import resolve_global_macros
        agent_config["system_prompt"] = resolve_global_macros(agent_config["system_prompt"], transition_data)
    except Exception as e:
        print(f"[Task] Erro ao resolver macros globais: {e}")

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
            asyncio.create_task(_auto_summarize_mtm_to_ltm(agent_id, session_id))

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


async def _auto_summarize_mtm_to_ltm(agent_id: str, session_id: str):
    """Auto-summarize MTM conversation into qualitative LTM facts."""
    try:
        from app.models.conversation_message import ConversationMessage
        from sqlalchemy import select
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage
        from app.weaviate_client import get_weaviate
        import uuid

        async with AsyncSessionLocal() as db:
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

def _match_true_trigger_keyword(message: str, keyword: str, mode: str) -> bool:
    """Deterministic matcher for true trigger keywords."""
    import re

    if not message or not keyword:
        return False

    message_norm = str(message).lower()
    keyword_norm = str(keyword).strip().lower()
    if not keyword_norm:
        return False

    mode_norm = (mode or "word").strip().lower()

    if mode_norm == "contains":
        return keyword_norm in message_norm

    if mode_norm == "phrase":
        msg_clean = " ".join(message_norm.split())
        kw_clean = " ".join(keyword_norm.split())
        return kw_clean in msg_clean

    escaped = re.escape(keyword_norm)
    return re.search(rf"(?<!\w){escaped}(?!\w)", message_norm) is not None


async def _build_collaborator_tools(
    db,
    agent_model,
    message: str,
    context_data: Optional[Dict[str, Any]] = None,
    user_access_level: str = "normal",
) -> tuple[list, list, list]:
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
        return [], [], []

    enabled = []
    neutral = []
    always_start = []
    always_end = []
    for setting in agent_with_settings.collaborator_settings:
        if setting.status == CollaborationStatus.ENABLED:
            enabled.append(setting.collaborator)
        elif setting.status == CollaborationStatus.NEUTRAL:
            neutral.append(setting.collaborator)
        elif setting.status == CollaborationStatus.ALWAYS_ACTIVE_START:
            always_start.append(setting.collaborator)
        elif setting.status == CollaborationStatus.ALWAYS_ACTIVE_END:
            always_end.append(setting.collaborator)
    all_collaborators = always_start + enabled + neutral + always_end
    if not all_collaborators:
        return [], [], []

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
        return [], [], []

    tools = []
    mandatory_instructions = []
    deterministic_matches = []

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
        
        # TRUE TRIGGER MATCHING (deterministic)
        true_agent_kws = getattr(collab, 'true_trigger_keywords', []) or []
        true_match_mode = getattr(collab, 'true_trigger_match_mode', 'word') or 'word'
        best_true_match = None
        for tkw in true_agent_kws:
            if _match_true_trigger_keyword(message, tkw, true_match_mode):
                candidate = {
                    "agent": collab,
                    "keyword": tkw,
                    "mode": true_match_mode,
                    "priority": 1 if collab in enabled else 2,
                    "keyword_len": len((tkw or "").strip()),
                }
                if best_true_match is None or candidate["keyword_len"] > best_true_match["keyword_len"]:
                    best_true_match = candidate

        if best_true_match:
            deterministic_matches.append(best_true_match)

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
        _response_style = getattr(collab, "response_style", "structured")

        async def _invoke_collab(instrucao: str, _agent=_collab, _database=_db, _ctx=_context_data, _planner_enabled=_is_planner, _p_prompt=_planner_prompt, _p_model=_planner_model, _r_style=_response_style) -> str:
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
                    response_style=_r_style,
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

    deterministic_matches.sort(key=lambda m: (m["priority"], -m["keyword_len"], (m["agent"].name or "").lower()))
    return tools, mandatory_instructions, deterministic_matches


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
    ib_global_search = getattr(agent_obj, "information_bases_global_search_enabled", False)

    if ib_global_search:
        fallback_user_id = None
        for ib in active_bases:
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
                        fallback_user_id = str(val).strip() or None
                        if fallback_user_id:
                            break

        if not fallback_user_id:
            for k, v in ctx.items():
                if isinstance(v, str) and v.strip():
                    fallback_user_id = v.strip()
                    break

        if fallback_user_id:
            import re
            _base_codes = [b.code for b in active_bases if b.code]
            _base_names = [b.name for b in active_bases if b.code]
            _uid = fallback_user_id
            _wc = weaviate_cl
            _m = max([getattr(b, 'max_results', 3) or 3 for b in active_bases] or [3])

            async def _search_global_bases(query: str, _codes=_base_codes, _names=_base_names, _u=_uid, _w=_wc, _max=_m) -> str:
                try:
                    results = await _w.search_information_bases(
                        base_codes=_codes,
                        user_id=_u,
                        query=query,
                        limit=_max,
                    )
                    if not results:
                        return "Nenhum resultado encontrado nas bases globais associadas."
                    lines = [f"- [{r.get('base_code', 'N/A')}] {r['content']}" for r in results]
                    return f"Resultados das bases globais ({', '.join(_names)}):\n" + "\n".join(lines)
                except Exception as e:
                    return f"Erro ao pesquisar bases globais: {str(e)}"

            global_tool = StructuredTool.from_function(
                coroutine=_search_global_bases,
                name="pesquisar_bases_globais",
                description=(
                    "Pesquisa global nas bases de informação associadas a este agente. "
                    "Use para buscar em todas as bases vinculadas em uma única consulta."
                ),
                return_direct=False,
            )
            tools.append(global_tool)
            print(f"[Task] 🔧 Global Information Base tool created: pesquisar_bases_globais (bases={len(_base_codes)}, user_id={fallback_user_id})")

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

# ─────────────────────────────────────────────────────────────
# Anti-Bot Guard — detect AI/bot interlocutors
# ─────────────────────────────────────────────────────────────

async def _check_anti_bot_guard(session_id: str, history: list) -> bool:
    """
    Anti-Bot Guard: every 5 user messages, analyze if interlocutor is a bot.
    Returns True if the session should be BLOCKED (bot detected), False otherwise.
    """
    try:
        # Increment counter
        count = await redis_client.increment_antibot_counter(session_id)

        # Only check every 5 messages
        if count % 5 != 0:
            return False

        # Collect only user messages from history (last 5)
        user_messages = [
            msg.get("content", "") for msg in history
            if msg.get("role") == "user"
        ][-5:]

        if len(user_messages) < 5:
            return False

        # Build analysis prompt
        messages_block = "\n".join([f"MSG {i+1}: {m}" for i, m in enumerate(user_messages)])

        detection_prompt = (
            "Você é um sistema de detecção de bots/IA. Analise as 5 mensagens abaixo de um suposto HUMANO "
            "conversando via WhatsApp e determine se ele parece ser outra IA/bot ou um humano real.\n\n"
            "INDICADORES DE BOT/IA:\n"
            "- Respostas perfeitamente estruturadas com bullet points, headers ou formatação markdown\n"
            "- Ausência total de erros de digitação, gírias, abreviações ou informalidade\n"
            "- Respostas excessivamente longas e completas para uma conversa casual de WhatsApp\n"
            "- Padrão repetitivo de estrutura (todas as respostas seguem o mesmo molde)\n"
            "- Uso excessivo de emojis de forma pré-formatada/mecânica\n"
            "- Linguagem que parece instruções a um assistente ou respostas de assistente\n\n"
            "INDICADORES DE HUMANO:\n"
            "- Erros de digitação, abreviações (vc, tb, pq, blz)\n"
            "- Mensagens curtas e diretas típicas de WhatsApp\n"
            "- Variação natural no tamanho e estilo das mensagens\n"
            "- Gírias, informalidade, expressões coloquiais\n"
            "- Respostas que fazem sentido no contexto de uma conversa real\n\n"
            f"MENSAGENS DO SUPOSTO HUMANO:\n{messages_block}\n\n"
            "Responda EXCLUSIVAMENTE com uma destas duas palavras:\n"
            "BOT_DETECTED — se parecer ser uma IA/bot\n"
            "HUMAN_OK — se parecer ser um humano real"
        )

        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            api_key=settings.OPENAI_API_KEY,
            max_tokens=20,
        )

        response = await llm.ainvoke([
            SystemMessage(content="You are a bot detection system. Reply only with BOT_DETECTED or HUMAN_OK."),
            HumanMessage(content=detection_prompt),
        ])

        verdict = response.content.strip().upper()
        print(f"[AntiBot] 🔍 Session {session_id}: message count={count}, verdict={verdict}")

        if "BOT_DETECTED" in verdict:
            await redis_client.set_antibot_blocked(session_id, ttl=3600)
            print(f"[AntiBot] 🚫 Session {session_id} BLOCKED — bot detected! TTL=1h")
            return True

        return False

    except Exception as e:
        print(f"[AntiBot] ⚠️ Error in anti-bot guard: {e}")
        return False  # Never block on error — fail open


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
                    
                    # Auto-map transition data based on agent schema if not provided
                    if agent.transition_input_schema and not transition_data:
                        trans_keys = set(agent.transition_input_schema.keys())
                        if context_data:
                            t_data = {}
                            for k in trans_keys:
                                if k in context_data:
                                    t_data[k] = context_data[k]
                            if t_data:
                                transition_data = t_data

            # Job Status Updates Monitor - Sync with consumer logic
            if callback_url:
                is_structured = bool(agent_config.get("output_schema")) if agent_config else False

                monitor = StatusMonitor(
                    callback_url=callback_url,
                    agent_config={
                        "status_updates_enabled": getattr(agent, "status_updates_enabled", True) if agent else True,
                        "status_updates_config": getattr(agent, "status_updates_config", {}) if agent else {}
                    },
                    session_id=session_id,
                    start_time=start_time,
                    transition_data=transition_data,
                    is_structured=is_structured
                )
                await monitor.start()
                # Initial state is handled by the loop delay and default moment

            if not agent_config:
                # No specific agent → fallback to Supervisor router
                from app.orchestrator import run_orchestrator_v2

                # STM: get history
                history = await redis_client.get_conversation(session_id)
                await redis_client.add_message(
                    session_id=session_id, role="user", content=message, ttl_seconds=86400,
                    tz_name=_resolve_tz_name(transition_data)
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

                # Strip internal metadata tags
                _ctx_re = re.compile(r'\[CONTEXTO_TEMPORAL:\s*[^\]]*\]\s*')
                if isinstance(final_result, str):
                    final_result = _ctx_re.sub('', final_result).strip()

                # Process response_variables - substituição de palavras na resposta
                response_vars = agent_config.get("config", {}).get("response_variables", [])
                if response_vars and isinstance(final_result, str):
                    for var in response_vars:
                        from_word = var.get("from", "")
                        to_template = var.get("to", "")
                        if from_word and to_template:
                            resolved = _resolve_template(to_template, context_data or {})
                            final_result = final_result.replace(from_word, resolved)

                if str(final_result).strip():
                    await redis_client.add_message(
                        session_id=session_id, role="assistant",
                        content=str(final_result), ttl_seconds=86400,
                        tz_name=_resolve_tz_name(transition_data)
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
                    content=message, ttl_seconds=stm_ttl_seconds,
                    tz_name=_resolve_tz_name(transition_data)
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

            # ═══════════════════════════════════════════════════════
            # GUARD: Anti-Bot Detection
            # ═══════════════════════════════════════════════════════
            if session_id:
                # Fast path: check if already blocked
                if await redis_client.is_antibot_blocked(session_id):
                    print(f"[AntiBot] 🚫 Session {session_id} is BLOCKED (bot). Returning silence.")
                    processing_time = (time.time() - start_time) * 1000
                    return {
                        "status": "completed",
                        "response": "",
                        "agent_used": "AntiBot Guard",
                        "processing_time_ms": processing_time,
                    }

                # Periodic check every 5 messages
                is_bot = await _check_anti_bot_guard(session_id, history)
                if is_bot:
                    print(f"[AntiBot] 🚫 Session {session_id} just got BLOCKED. Returning silence.")
                    processing_time = (time.time() - start_time) * 1000
                    return {
                        "status": "completed",
                        "response": "",
                        "agent_used": "AntiBot Guard",
                        "processing_time_ms": processing_time,
                    }

            # Build LangChain messages
            user_tz_name = _resolve_tz_name(transition_data)
            messages = []
            for msg in history:
                timestamp = msg.get("created_at") or msg.get("timestamp")
                # Convert timestamp to user's local timezone for display
                if timestamp:
                    try:
                        from datetime import datetime as _dt
                        try:
                            from zoneinfo import ZoneInfo as _ZI
                        except ImportError:
                            import pytz
                            _ZI = pytz.timezone
                        parsed = _dt.fromisoformat(timestamp)
                        local_dt = parsed.astimezone(_ZI(user_tz_name))
                        timestamp = local_dt.strftime('%d/%m/%Y %H:%M:%S')
                    except Exception:
                        pass  # keep original string on any parse error
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

            # [THINKER] Internal thinking step with task list management
            thinker_enabled = False
            think_task_list = None
            try:
                from app.models.agent import Agent as AgentModel
                from sqlalchemy import select
                
                agent_id = agent_config.get("id")
                if agent_id:
                    result = await db.execute(select(AgentModel).where(AgentModel.id == agent_id))
                    agent_model = result.scalar_one_or_none()
                else:
                    agent_model = agent_config.get("agent_model")
                
                print(f"[Task] 🔍 DEBUG Thinker - agent_model: {agent_model}")
                
                if agent_model:
                    is_thinker = getattr(agent_model, 'is_thinker', False)
                    thinker_always_active = getattr(agent_model, 'thinker_always_active', False)
                    thinker_keywords = getattr(agent_model, 'thinker_keywords', None) or []
                    trigger_keywords = getattr(agent_model, 'trigger_keywords', None) or []
                    thinker_memory_enabled = getattr(agent_model, 'thinker_memory_enabled', True)  # Default True
                    
                    print(f"[Task] 🔍 DEBUG Thinker - is_thinker: {is_thinker}, always_active: {thinker_always_active}, memory_enabled: {thinker_memory_enabled}, keywords: {thinker_keywords}, trigger: {trigger_keywords}")
                    
                    # Check agent memory for existing task list (only if memory is enabled)
                    # Use get_redis() to ensure we get the instance properly
                    _redis = await get_redis()
                    
                    # Resume from existing task list only if memory is enabled
                    if thinker_memory_enabled:
                        agent_memory = await _redis.get_agent_memory(session_id, str(agent_model.id))
                        
                        if agent_memory and agent_memory.get("task_list") and agent_memory.get("status") == "in_progress":
                            # Resume from existing task list - don't call Thinker again
                            think_task_list = agent_memory.get("task_list")
                            current_task = agent_memory.get("current_task", 1)
                            print(f"[Task] 🧠 Resuming Thinker task list from memory - current task: {current_task}, total: {len(think_task_list)}")
                            
                            # Inject task list into prompt for continuation
                            task_list_text = "\n".join([f"[{'✓' if t.get('completed') else ' '}] Task {i+1}: {t.get('description', t.get('acao', 'N/A'))}" 
                                                        for i, t in enumerate(think_task_list)])
                            
                            continuation_instruction = (
                                f"\n\n## 🧠 LISTA DE TAREFAS EM ANDAMENTO\n\n"
                                f"Você está continuando uma lista de tarefas criada pelo Thinker. "
                                f"Marque as tarefas já concluídas com ✓.\n\n"
                                f"{task_list_text}\n\n"
                                f"🎯 Próxima tarefa a executar: Task {current_task}\n"
                                f"Instruções: Execute a tarefa atual, marque como concluída (✓), e avance para a próxima.\n"
                                f"⚠️ NÃO use o Thinker novamente - continue a partir da lista existente.\n"
                            )
                            agent_config["system_prompt"] = agent_config.get("system_prompt", "") + continuation_instruction
                            thinker_enabled = True  # Thinker was already used, just continuing
                    
                    if not thinker_enabled and is_thinker:
                        # Check if Thinker should be activated (only if no existing task list)
                        if thinker_always_active:
                            thinker_enabled = True
                            print(f"[Task] 🧠 Thinker always active for agent '{agent_model.name}'")
                        else:
                            message_lower = message.lower()
                            all_keywords = list(thinker_keywords) + list(trigger_keywords)
                            print(f"[Task] 🔍 DEBUG Thinker - checking keywords: {all_keywords} in message: {message_lower[:50]}...")
                            for kw in all_keywords:
                                if kw.lower() in message_lower:
                                    thinker_enabled = True
                                    print(f"[Task] 🧠 Thinker activated by keyword: '{kw}'")
                                    break
                        
                        # If Thinker is enabled, call it to create task list
                        if thinker_enabled:
                            from app.services.thinker_service import call_thinker
                            from uuid import UUID
                            
                            # Prepare context for Thinker
                            context_for_thinker = {
                                "agent_id": str(agent_model.id),
                                "agent_name": agent_model.name,
                                "session_id": session_id,
                            }
                            if context_data:
                                context_for_thinker.update(context_data)
                            
                            print(f"[Task] 🧠 Calling Thinker to generate task list for '{agent_model.name}'...")
                            
                            thinker_result = await call_thinker(
                                db=db,
                                thinker=agent_model,
                                message=message,
                                context_data=context_for_thinker,
                                history=[]
                            )
                            
                            # Parse the Thinker response to get task list
                            passos = thinker_result.get("passos", [])
                            if passos:
                                # Convert Thinker response to task list format
                                think_task_list = []
                                for passo in passos:
                                    think_task_list.append({
                                        "ordem": passo.get("ordem", 0),
                                        "agente": passo.get("agente", ""),
                                        "acao": passo.get("acao", ""),
                                        "dados_necessarios": passo.get("dados_necessarios", {}),
                                        "completed": False,
                                        "description": passo.get("acao", "")
                                    })
                                
                                # Save task list to agent memory (only if memory is enabled)
                                if thinker_memory_enabled:
                                    _redis = await get_redis()
                                    await _redis.set_agent_memory(
                                        session_id=session_id,
                                        agent_id=str(agent_model.id),
                                        memory_data={
                                            "task_list": think_task_list,
                                            "current_task": 1,
                                            "status": "in_progress",
                                            "visao_geral": thinker_result.get("visao_geral", ""),
                                            "original_message": message,
                                            "created_at": str(datetime.now())
                                        },
                                        ttl_seconds=3600
                                    )
                                    print(f"[Task] 🧠 Thinker generated {len(think_task_list)} tasks, saved to agent memory")
                                
                                # Inject task list into prompt
                                task_list_text = "\n".join([f"[ ] Task {t.get('ordem')}: {t.get('acao')}" for t in think_task_list])
                                
                                thinking_instruction = (
                                    f"\n\n## 🧠 THINKER ATIVADO - PLANO DE EXECUÇÃO GERADO\n\n"
                                    f"{thinker_result.get('visao_geral', '')}\n\n"
                                    f"📋 Lista de Tarefas (SIGA IMPRETERIVELMENTE):\n"
                                    f"{task_list_text}\n\n"
                                    f"🎯 Execute a Task 1 primeiro, marque como concluída (✓), e avance para a próxima.\n"
                                    f"⚠️ Após completar todas as tarefas, limpe a memória do Thinker.\n"
                                )
                                
                                agent_config["system_prompt"] = agent_config.get("system_prompt", "") + thinking_instruction
                                print(f"[Task] 🧠 Thinker task list injected for agent '{agent_model.name}'")
                                
                                # NOTE: thinker_model is used ONLY in call_thinker, not on main agent
                            else:
                                print(f"[Task] ⚠️ Thinker did not return valid task list")
                                # Fallback to simple instruction
                                thinker_prompt = getattr(agent_model, 'thinker_prompt', None) or (
                                    "Você é um assistente de IA estratégico. Antes de responder, analise a solicitação do usuário "
                                    "e identifique os passos necessários para resolver a tarefa de forma eficaz."
                                )
                                is_restrictive = getattr(agent_model, 'thinker_restrictive', False)
                                
                                if is_restrictive:
                                    thinking_instruction = (
                                        f"\n\n## 🧠 MODO THINKER ATIVADO - ANÁLISE OBRIGATÓRIA\n\n"
                                        f"⚠️ **IMPORTANTE**: Antes de responder, você DEVE analisar a solicitação e seguir estas regras:\n\n"
                                        f"1. Analise a solicitação do usuário com cuidado\n"
                                        f"2. Identifique os passos necessários para executar a tarefa\n"
                                        f"3. Considere usar os colaboradores/tools disponíveis\n"
                                        f"4. Execute APENAS o que for necessário\n"
                                        f"5. NÃO invente informações ou execute tarefas não solicitadas\n\n"
                                        f"📝 Instrução do Thinker: {thinker_prompt}\n"
                                    )
                                else:
                                    thinking_instruction = (
                                        f"\n\n## 🧠 THINKER ATIVADO\n\n"
                                        f"Antes de responder, considere: {thinker_prompt}\n"
                                    )
                                
                                agent_config["system_prompt"] = agent_config.get("system_prompt", "") + thinking_instruction
                                print(f"[Task] 🧠 Thinker enabled for agent '{agent_model.name}' (fallback mode)")
                            
            except Exception as e:
                import traceback
                print(f"[Task] ⚠️ Error in thinker processing: {e}")
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
                    output_text = output_text.replace("[FIM_DE_INTERACAO]", "").strip()
                    if not output_text:
                        if isinstance(final_result, dict):
                            final_result["output"] = ""
                        else:
                            final_result = ""
                    else:
                        if isinstance(final_result, dict):
                            final_result["output"] = output_text
                        else:
                            final_result = output_text
                    print(f"[Task] 🛑 Interação finalizada silenciosamente pelo agente {agent_used}")

                # Limpar Tag de HITL caso exista
                is_hitl_pause = False
                if "{{ $HITL }}" in output_text:
                    output_text = output_text.replace("{{ $HITL }}", "").strip()
                    is_hitl_pause = True
                    if isinstance(final_result, dict):
                        final_result["output"] = output_text
                    else:
                        final_result = output_text
                    print(f"[Task] 🛑 Intervenção Humana (HITL) solicitada pelo agente {agent_used}")

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

                # Strip internal metadata tags that may leak into the response
                _ctx_re = re.compile(r'\[CONTEXTO_TEMPORAL:\s*[^\]]*\]\s*')
                output_text = _ctx_re.sub('', output_text).strip()
                if isinstance(final_result, str):
                    final_result = _ctx_re.sub('', final_result).strip()

                # Process response_variables - substituição de palavras na resposta
                response_vars = agent_config.get("config", {}).get("response_variables", [])
                if response_vars and isinstance(final_result, str):
                    for var in response_vars:
                        from_word = var.get("from", "")
                        to_template = var.get("to", "")
                        if from_word and to_template:
                            resolved = _resolve_template(to_template, context_data or {})
                            final_result = final_result.replace(from_word, resolved)

                # Mandatory final collaborators: ALWAYS_ACTIVE_END
                if agent_model and getattr(agent_model, "is_orchestrator", False) and getattr(agent_model, "collaboration_enabled", False):
                    try:
                        from app.orchestrator.agent_orchestrator import AgentOrchestrator
                        from app.models.agent import CollaborationStatus

                        orchestrator = AgentOrchestrator(db, monitor=monitor)
                        agent_with_settings = await orchestrator.get_agent_with_collaborators(agent_model.id)
                        always_end_collabs = []
                        if agent_with_settings and agent_with_settings.collaborator_settings:
                            for setting in agent_with_settings.collaborator_settings:
                                if setting.status == CollaborationStatus.ALWAYS_ACTIVE_END:
                                    always_end_collabs.append(setting.collaborator)

                        if always_end_collabs:
                            final_text_for_formatter = str(final_result) if not isinstance(final_result, str) else final_result
                            for collab in always_end_collabs:
                                orientation = (
                                    "MANDATORY_ALWAYS_ACTIVE_END: você deve finalizar e formatar a resposta final ao usuário. "
                                    "Use o conteúdo abaixo como base e entregue apenas a resposta final, pronta para o usuário.\n\n"
                                    f"RESPOSTA_BASE_DO_ORQUESTRADOR:\n{final_text_for_formatter}"
                                )
                                collab_name, collab_response = await orchestrator._invoke_collaborator(
                                    agent=collab,
                                    message=final_text_for_formatter,
                                    history=history or [],
                                    context=rag_context or "",
                                    context_data=context_data,
                                    orientation=orientation,
                                    primary_agent=agent_model,
                                    monitor=monitor,
                                    response_style=getattr(collab, "response_style", "structured"),
                                )
                                if collab_response and str(collab_response).strip():
                                    final_text_for_formatter = str(collab_response).strip()
                                    print(f"[Task] ✅ ALWAYS_ACTIVE_END aplicado por '{collab_name}'")

                            if isinstance(final_result, dict):
                                if "output" in final_result:
                                    final_result["output"] = final_text_for_formatter
                                elif "response" in final_result:
                                    final_result["response"] = final_text_for_formatter
                                else:
                                    final_result = final_text_for_formatter
                            else:
                                final_result = final_text_for_formatter
                            output_text = final_text_for_formatter
                    except Exception as e:
                        print(f"[Task] ⚠️ Error executing ALWAYS_ACTIVE_END collaborators: {e}")

                if output_text.strip():
                    if stm_enabled:
                        await redis_client.add_message(
                            session_id=session_id, role="assistant",
                            content=output_text, ttl_seconds=stm_ttl_seconds,
                            tz_name=_resolve_tz_name(transition_data)
                        )
                    # MTM: save assistant response
                    if agent_id and session_id:
                        await _save_mtm_message(db, agent_id, session_id, "assistant", output_text)

                processing_time = (time.time() - start_time) * 1000
                response_data = {
                    "status": "completed",
                    "agent_used": agent_used,
                    "processing_time_ms": processing_time,
                    "is_hitl_pause": is_hitl_pause,
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
                    tz_name=_resolve_tz_name(transition_data),
                )
                response_data["last_agent"] = agent_used
                print(f"[Task] 💾 Session context saved: last_agent='{agent_used}'")
                
                # [THINKER] Update task list in agent memory if Thinker was used
                if think_task_list:
                    agent_memory = await redis_client.get_agent_memory(session_id, str(agent_id))
                    if agent_memory and agent_memory.get("task_list"):
                        # Check if response indicates task completion (look for patterns like "[Task 1 concluída]" or similar)
                        response_lower = output_text.lower()
                        
                        # Simple heuristic: if response contains success indicators, mark current task as complete
                        updated = False
                        task_list = agent_memory.get("task_list", [])
                        current_task = agent_memory.get("current_task", 1)
                        
                        # Find and mark completed tasks based on response content
                        for i, task in enumerate(task_list):
                            if not task.get("completed"):
                                task_acao = task.get("acao", "").lower()
                                # If response mentions something related to the task action
                                if any(word in response_lower for word in ["sucesso", "concluído", "concluida", "registrado", "confirmado", "ok", "realizado", "efetivado"]):
                                    task["completed"] = True
                                    current_task = i + 2  # Move to next task
                                    updated = True
                                    print(f"[Task] ✓ Task {i+1} marked as completed in memory")
                                    break
                        
                        if updated:
                            # Update memory with new task list
                            await redis_client.update_agent_memory(
                                session_id=session_id,
                                agent_id=str(agent_id),
                                updates={
                                    "task_list": task_list,
                                    "current_task": current_task,
                                },
                                ttl_seconds=3600
                            )
                            
                            # Check if all tasks are completed
                            all_completed = all(t.get("completed", False) for t in task_list)
                            if all_completed:
                                print(f"[Task] 🧠 All Thinker tasks completed! Clearing agent memory...")
                                await redis_client.delete_agent_memory(session_id, str(agent_id))
                                response_data["thinker_completed"] = True
                                
            except Exception as e:
                print(f"[Task] ⚠️ Failed to save session context: {e}")

            # Agent self-correction: detect prompt violations in background (only for substantive responses)
            if vector_memory_enabled and agent_id and final_result:
                agent_response_str = str(final_result) if not isinstance(final_result, str) else final_result
                try:
                    from app.services.memory_gate import should_extract_memories
                    if should_extract_memories(message, agent_response_str, history):
                        from app.services.vector_memory_service import extract_agent_self_corrections
                        import asyncio
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
                content=friendly_message, ttl_seconds=86400,
                tz_name=_resolve_tz_name(transition_data) if 'transition_data' in locals() and transition_data else None
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
