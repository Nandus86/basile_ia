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
            base_codes = [b.code for b in ib_agent.information_bases if b.is_active]
            if base_codes:
                possible_ids = []
                ctx = context_data or {}
                for v in ctx.values():
                    if isinstance(v, str) and v.strip():
                        possible_ids.append(v.strip())
                if session_id:
                    possible_ids.append(str(session_id))

                weaviate_cl = get_weaviate()
                if weaviate_cl and possible_ids:
                    all_info_nodes = []
                    for uid in possible_ids:
                        info_nodes = await weaviate_cl.search_information_bases(
                            base_codes=base_codes, user_id=uid, query=message, limit=5
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

    # 3. Vector Memory
    vector_memory_enabled = getattr(agent_config.get("agent_model"), "vector_memory_enabled", False)
    if vector_memory_enabled and agent_id and session_id:
        try:
            from app.weaviate_client import get_weaviate
            weaviate_client = get_weaviate()
            if weaviate_client:
                memories = await weaviate_client.search_contact_memories(
                    agent_id=str(agent_id),
                    contact_id=str(session_id),
                    query=message,
                    limit=5,
                )
                if memories:
                    print(f"[Task] 🧠 Retrieved {len(memories)} qualitative facts for contact {session_id}")
                    mem_str = "\n".join([f"- {m['content']}" for m in memories])
                    agent_config["system_prompt"] = agent_config.get("system_prompt", "") + (
                        f"\n\n## Inteligência e Memória Histórica do Contato\n\n"
                        f"Abaixo estão informações e peculiaridades qualitativas deste usuário, "
                        f"adquiridas em interações anteriores. "
                        f"Utilize isso para personalizar ativamente o engajamento de maneira natural:\n\n"
                        f"{mem_str}\n"
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

    # 4. Orchestrator Pre-Consultation (fires for any agent with collaboration or orchestrator mode)
    agent_model = agent_config.get("agent_model")
    print(f"[Task] 🔍 ORCH DEBUG: agent_model={agent_model}, type={type(agent_model)}")
    if agent_model:
        print(f"[Task] 🔍 ORCH DEBUG: is_orchestrator={getattr(agent_model, 'is_orchestrator', 'MISSING')}, collaboration_enabled={getattr(agent_model, 'collaboration_enabled', 'MISSING')}")
    
    if agent_model and (getattr(agent_model, "is_orchestrator", False) or getattr(agent_model, "collaboration_enabled", False)):
        print(f"[Task] 🔍 ORCH DEBUG: ENTERING pre-consultation block for {agent_config['name']}")
        try:
            from app.orchestrator.agent_orchestrator import AgentOrchestrator

            orchestrator = AgentOrchestrator(db)
            print(f"[Task] 🔍 ORCH DEBUG: Calling gather_subordinate_responses with agent_id={getattr(agent_model, 'id', 'UNKNOWN')}")
            subordinate_context = await orchestrator.gather_subordinate_responses(
                message=message,
                primary_agent=agent_model,
                context=rag_context or "",
                context_data=context_data,
                history=history,
                session_id=session_id,
            )
            print(f"[Task] 🔍 ORCH DEBUG: gather_subordinate_responses returned: '{subordinate_context[:200] if subordinate_context else 'EMPTY'}'")
            if subordinate_context:
                print(f"[Task] 🎭 Orchestrator pre-consult loaded for {agent_config['name']}")
                agent_config["system_prompt"] = agent_config.get("system_prompt", "") + (
                    f"\n\n## Colaboradores (Subordinados)\n"
                    f"Os seguintes especialistas forneceram análises sobre a solicitação do usuário. "
                    f"Sintetize e utilize as informações relevantes para construir a resposta final:\n"
                    f"{subordinate_context}\n"
                )
            else:
                print(f"[Task] 🔍 ORCH DEBUG: No subordinate context returned (empty string)")
        except Exception as e:
            import traceback
            print(f"[Task] Orchestrator pre-consultation error: {e}")
            traceback.print_exc()
    else:
        print(f"[Task] 🔍 ORCH DEBUG: SKIPPING pre-consultation (condition not met)")

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
            if stm_enabled:
                history = await redis_client.get_conversation(session_id)
                await redis_client.add_message(
                    session_id=session_id, role="user",
                    content=message, ttl_seconds=stm_ttl_seconds
                )

            # Build LangChain messages
            messages = []
            for msg in history:
                if msg.get("role") == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg.get("role") == "assistant":
                    messages.append(AIMessage(content=msg["content"]))
            messages.append(HumanMessage(content=message))

            # Enrich prompt (RAG, InfoBases, VectorMemory, Orchestrator)
            rag_context = await _enrich_agent_prompt(
                db, agent_config, agent_id, message, session_id, context_data, history
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
