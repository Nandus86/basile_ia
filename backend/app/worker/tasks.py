"""
ARQ Task Definitions
These functions run inside the ARQ worker process, decoupled from the FastAPI request.
"""
import time
import json
from typing import Optional, Dict, Any, List

from app.database import AsyncSessionLocal
from app.redis_client import redis_client


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
    Background task: process a message through the orchestrator.
    Runs in the ARQ worker, not in the FastAPI process.
    """
    from app.orchestrator import run_orchestrator_v2
    
    start_time = time.time()
    
    try:
        # Create a fresh DB session for this worker task
        async with AsyncSessionLocal() as db:
            from app.orchestrator.agent_factory import AgentFactory
            
            # Check if target agent exists and has output schema
            agent_config = None
            factory = AgentFactory(db)
            if agent_id:
                agent = await factory.get_agent_by_id(agent_id)
                if agent:
                    agent_config = await factory.get_agent_config(agent)
            else:
                agents = await factory.get_accessible_agents(user_access_level)
                if agents:
                    agent_config = await factory.get_agent_config(agents[0])

            # Resolve STM configuration
            stm_enabled = True
            stm_ttl_seconds = 86400
            if agent_config and "config" in agent_config:
                cfg = agent_config["config"]
                stm_enabled = cfg.get("short_term_memory_enabled", True)
                stm_ttl_hours = cfg.get("short_term_memory_ttl_hours", 24)
                stm_ttl_seconds = int(stm_ttl_hours * 3600)

            # Get conversation history from Redis
            history = []
            if stm_enabled:
                history = await redis_client.get_conversation(session_id)
                
                # Add message to history
                await redis_client.add_message(
                    session_id=session_id,
                    role="user",
                    content=message,
                    ttl_seconds=stm_ttl_seconds
                )

            if agent_config and agent_config.get("output_schema"):
                from langchain_core.messages import HumanMessage, AIMessage
                # Run Structured Agent
                messages = []
                for msg in history:
                    if msg.get("role") == "user":
                        messages.append(HumanMessage(content=msg["content"]))
                    elif msg.get("role") == "assistant":
                        messages.append(AIMessage(content=msg["content"]))
                messages.append(HumanMessage(content=message))

                rag_context = None
                try:
                    from app.services.rag_service import get_rag_context
                    rag_context = await get_rag_context(db, agent_config["id"], message, limit=5)
                except Exception:
                    pass

                # Information Bases Retrieval
                try:
                    from app.models.agent import Agent as AgentModel
                    from sqlalchemy import select as sa_select
                    from sqlalchemy.orm import selectinload
                    from app.weaviate_client import get_weaviate
                    
                    ib_result = await db.execute(
                        sa_select(AgentModel).options(selectinload(AgentModel.information_bases)).where(AgentModel.id == agent_id)
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
                                    unique_nodes = [n for n in all_info_nodes if n['content'] not in seen and not seen.add(n['content'])]
                                    print(f"[Task] \U0001f4da Retrieved {len(unique_nodes)} Information Base contexts")
                                    info_str = "\n".join([f"- {n['content']} (Meta: {n['metadata']})" for n in unique_nodes[:10]])
                                    agent_config["system_prompt"] = agent_config.get("system_prompt", "") + f"\n\n## Contextualiza\u00e7\u00e3o Personalizada Externa\n\nInforma\u00e7\u00f5es anexadas aos bancos de dados do usu\u00e1rio logado:\n{info_str}\n"
                except Exception as ib_err:
                    print(f"[Task] Failed to retrieve Information Bases: {ib_err}")

                result_dict = await factory.invoke_agent_structured(
                    agent_config=agent_config,
                    messages=messages,
                    rag_context=rag_context,
                    context_data=context_data
                )
                
                print(f"[DEBUG] Structured Result Dict: {result_dict}, type: {type(result_dict)}")
                
                # Store serialized dictionary response
                response_text = result_dict if isinstance(result_dict, dict) else result_dict.get("output", str(result_dict))
                
                final_result = response_text
                agent_used = agent_config["name"]
            
            else:
                # Run Standard Orchestrator V2
                result = await run_orchestrator_v2(
                    message=message,
                    session_id=session_id,
                    history=history,
                    agent_id=agent_id,
                    db=db,
                    user_access_level=user_access_level,
                    context_data=context_data,
                )
                final_result = result["response"]
                agent_used = result.get("agent_used")

        # Store response in history
        if stm_enabled:
            await redis_client.add_message(
                session_id=session_id,
                role="assistant",
                content=str(final_result),
                ttl_seconds=stm_ttl_seconds
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
            import httpx
            import asyncio
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(callback_url, json=response_data, timeout=10.0)
            except Exception as cb_err:
                print(f"Failed to send callback to {callback_url}: {cb_err}")

        return response_data
        
    except Exception as e:
        processing_time = (time.time() - start_time) * 1000
        return {
            "status": "failed",
            "response": f"Error processing message: {str(e)}",
            "error": str(e),
            "processing_time_ms": processing_time,
        }


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
    """
    from app.orchestrator.agent_factory import AgentFactory
    from langchain_core.messages import HumanMessage, AIMessage
    
    start_time = time.time()
    
    try:
        async with AsyncSessionLocal() as db:
            factory = AgentFactory(db)
            
            # Get agent
            if agent_id:
                agent = await factory.get_agent_by_id(agent_id)
            else:
                agents = await factory.get_accessible_agents(user_access_level)
                agent = agents[0] if agents else None
            
            if not agent:
                return {
                    "status": "completed",
                    "output": "Nenhum agente disponível.",
                    "agent_used": None,
                    "processing_time_ms": (time.time() - start_time) * 1000,
                }
            
            agent_config = await factory.get_agent_config(agent)
            
            # Resolve STM configuration
            stm_enabled = True
            stm_ttl_seconds = 86400
            if agent_config and "config" in agent_config:
                cfg = agent_config["config"]
                stm_enabled = cfg.get("short_term_memory_enabled", True)
                stm_ttl_hours = cfg.get("short_term_memory_ttl_hours", 24)
                stm_ttl_seconds = int(stm_ttl_hours * 3600)
                
            # Get conversation history
            history = []
            if stm_enabled:
                history = await redis_client.get_conversation(session_id)
                
                # Add message to history
                await redis_client.add_message(
                    session_id=session_id,
                    role="user",
                    content=message,
                    ttl_seconds=stm_ttl_seconds
                )
            
            # Build messages
            messages = []
            for msg in history:
                if msg.get("role") == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg.get("role") == "assistant":
                    messages.append(AIMessage(content=msg["content"]))
            messages.append(HumanMessage(content=message))
            
            # Get RAG context
            rag_context = None
            try:
                from app.services.rag_service import get_rag_context
                rag_context = await get_rag_context(db, agent_config["id"], message, limit=5)
            except Exception:
                pass
            
            # Information Bases Retrieval
            try:
                from app.models.agent import Agent as AgentModel
                from sqlalchemy import select as sa_select
                from sqlalchemy.orm import selectinload
                from app.weaviate_client import get_weaviate
                
                ib_result = await db.execute(
                    sa_select(AgentModel).options(selectinload(AgentModel.information_bases)).where(AgentModel.id == agent_id)
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
                                unique_nodes = [n for n in all_info_nodes if n['content'] not in seen and not seen.add(n['content'])]
                                print(f"[Task] \U0001f4da Retrieved {len(unique_nodes)} Information Base contexts")
                                info_str = "\n".join([f"- {n['content']} (Meta: {n['metadata']})" for n in unique_nodes[:10]])
                                agent_config["system_prompt"] = agent_config.get("system_prompt", "") + f"\n\n## Contextualiza\u00e7\u00e3o Personalizada Externa\n\nInforma\u00e7\u00f5es anexadas aos bancos de dados do usu\u00e1rio logado:\n{info_str}\n"
            except Exception as ib_err:
                print(f"[Task] Failed to retrieve Information Bases: {ib_err}")
            
            # Invoke structured
            result = await factory.invoke_agent_structured(
                agent_config=agent_config,
                messages=messages,
                rag_context=rag_context,
                context_data=context_data,
            )
        
        # Store response
        output_text = result.get("output", str(result))
        if stm_enabled:
            await redis_client.add_message(
                session_id=session_id,
                role="assistant",
                content=output_text,
                ttl_seconds=stm_ttl_seconds
            )
        
        processing_time = (time.time() - start_time) * 1000
        
        response_data = {
            "status": "completed",
            **result,
            "agent_used": agent_config["name"],
            "processing_time_ms": processing_time,
        }
        
        if transition_data:
            response_data["transition_data"] = transition_data
        
        if callback_url:
            import httpx
            import asyncio
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(callback_url, json=response_data, timeout=10.0)
            except Exception as cb_err:
                print(f"Failed to send callback to {callback_url}: {cb_err}")

        return response_data
        
    except Exception as e:
        processing_time = (time.time() - start_time) * 1000
        return {
            "status": "failed",
            "output": f"Erro: {str(e)}",
            "error": str(e),
            "processing_time_ms": processing_time,
        }
