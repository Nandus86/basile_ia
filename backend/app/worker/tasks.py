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
        # Get conversation history from Redis
        history = await redis_client.get_conversation(session_id)
        
        # Add message to history
        await redis_client.add_message(
            session_id=session_id,
            role="user",
            content=message
        )
        
        # Create a fresh DB session for this worker task
        async with AsyncSessionLocal() as db:
            from app.orchestrator.agent_factory import AgentFactory
            
            # Check if target agent exists and has output schema
            agent_config = None
            if agent_id:
                factory = AgentFactory(db)
                agent = await factory.get_agent_by_id(agent_id)
                if agent and agent.output_schema:
                    agent_config = await factory.get_agent_config(agent)

            if agent_config:
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
        await redis_client.add_message(
            session_id=session_id,
            role="assistant",
            content=str(final_result)
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
        # Get conversation history
        history = await redis_client.get_conversation(session_id)
        
        # Add message to history
        await redis_client.add_message(
            session_id=session_id,
            role="user",
            content=message
        )
        
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
            
            # Invoke structured
            result = await factory.invoke_agent_structured(
                agent_config=agent_config,
                messages=messages,
                rag_context=rag_context,
                context_data=context_data,
            )
        
        # Store response
        output_text = result.get("output", str(result))
        await redis_client.add_message(
            session_id=session_id,
            role="assistant",
            content=output_text
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
