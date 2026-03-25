"""
# Implementação do Treinamento Duplo Direcionado (Dual Training)

Este plano descreve como adicionaremos botões de treinamento manual duplo nas telas de histórico (Curto e Médio Praz# Dual Training na Memória

**Task Status:** Planning Dual Training Interface

- [ ] Modificar `backend/app/api/memory.py` para criar rota `/train-dual`.
- [ ] Modificar `frontend/src/views/MemoryManager.vue` para inserir botões nas mensagens (`👍👎`).
- [ ] Adicionar modal dinâmico no Frontend com duas TextAreas (Regra Agente, Regra Contato).
- [ ] Conectar o envio ao endpoint `/train-dual`.
- [ ] Enviar notificação de revisão do plano para o usuário.
- [ ] Aguardar aprovação para implementação (`notify_user`).a.

## Proposed Changes

### Frontend (UI)

#### [MODIFY] [MemoryManager.vue](file:///d:/projetos/Basile_IA_Orch/frontend/src/views/MemoryManager.vue)
- Na aba de visualização detalhada (`detailDialog`) de uma conversa STM ou MTM, adicionar botões de ação ("polegar para cima" e "polegar para baixo") visíveis em cada balão de mensagem do Agente (`msg.role === 'assistant'`).
- Criar um novo `<v-dialog v-model="dualTrainDialog">` que abre ao clicar nesses botões. O painel conterá:
  - O trecho da mensagem selecionada para contexto.
  - `<v-textarea>` 1: **Orientação para o usuário (Contato)** - Regra específica para o relacionamento deste Contato com a IA.
  - `<v-textarea>` 2: **Orientação para o Agente** - Regra para o agente aprender (Auto-Correção / Diretriz de Comportamento).
- Adicionar a função `submitDualTraining()` que enviará um POST para a API com as regras preenchidas no painel.
- Opcionalmente exibir identificador do `agent_id` e `session_id/contact_id` no cabeçalho do diálogo de treinamento para referência visual de quem receberá o treinamento.

### Backend (APIs)

#### [MODIFY] [memory.py](file:///d:/projetos/Basile_IA_Orch/backend/app/api/memory.py)
- Adicionar o novo endpoint `POST /memory/train-dual`.
- Endpoint aceitará um payload contendo:
  - `agent_id`
  - `contact_id`
  - `contact_rule` (opcional)
  - `agent_rule` (opcional)
  - `message_context` (opcional, um trecho da mensagem que iniciou o treinamento).
- Lógica:
  - Se `contact_rule` for recebido: Injeta no Weaviate usando `save_contact_memory(agent_id, contact_id, content="⚠️ REGRA ESPECÍFICA: " + contact_rule, memory_type="preference")`.
  - Se `agent_rule` for recebido: Injeta no Weaviate usando `save_agent_self_memory(agent_id, content="🔧 DIRETRIZ MANUAL: " + agent_rule, memory_type="self_correction")`.
- Retorna `{ "status": "success", "saved_contact": bool, "saved_agent": bool }`.

## Verification Plan

### Automated Tests
- Verificar na rede (Developer Tools) se o POST para `/memory/train-dual` transporta as chaves corretamente.

### Manual Verification
- Acessar "Meus Agentes" -> "Gerenciador de Memória".
- Abrir um histórico na aba MTM ou STM (clicando no ícone do olhinho).
- Na mensagem gerada pelo sistema, clicar no botão de Treinar (👍 / 👎).
- Preencher "Regra para o Contato" e "Regra para o Agente". Salvar e confirmar mensagem de Snackbar.
- Navegar para a aba "Memória Vetorial" e verificar se as duas inserções apareceram nas subguias "Contatos" e "Auto-Agente" respectivamente.
"""
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
from typing import Optional, List
import json

from app.redis_client import redis_client
from app.weaviate_client import weaviate_client

router = APIRouter()

class DualTrainRequest(BaseModel):
    agent_id: str
    contact_id: Optional[str] = None
    session_id: Optional[str] = None
    contact_rule: Optional[str] = None
    agent_rule: Optional[str] = None
    message_context: Optional[str] = None

# ─────────────────────────────────────────────────
# Dual Training (Manual RLHF)
# ─────────────────────────────────────────────────
@router.post("/train-dual")
async def train_dual_memory(payload: DualTrainRequest):
    """
    Saves specific manual rules for the Agent (Self-Correction/Instruction) 
    and/or for the Contact (User Preference/Fact).
    """
    if not payload.agent_rule and not payload.contact_rule:
        raise HTTPException(status_code=400, detail="Pelo menos uma regra (agente ou contato) deve ser fornecida.")
        
    saved_contact = False
    saved_agent = False
    
    # Identify contact reference
    contact_ref = payload.contact_id or payload.session_id
    
    metadata = {}
    if payload.message_context:
        metadata["trigger_message"] = payload.message_context[:500]
        
    if payload.contact_rule and contact_ref:
        saved_contact = await weaviate_client.save_contact_memory(
            agent_id=payload.agent_id,
            contact_id=contact_ref,
            content=f"⚠️ REGRA/PREFERÊNCIA MANUAL: {payload.contact_rule.strip()}",
            metadata=metadata,
            memory_type="preference"
        )
        
    if payload.agent_rule:
        saved_agent = await weaviate_client.save_agent_self_memory(
            agent_id=payload.agent_id,
            content=f"🔧 DIRETRIZ MANUAL: {payload.agent_rule.strip()}",
            metadata=metadata,
            memory_type="manual_rule"
        )
        
    return {
        "status": "success",
        "saved_contact": saved_contact,
        "saved_agent": saved_agent
    }


# ─────────────────────────────────────────────────
# STM (Redis) - Short-Term Memory (conversation:*)
# ─────────────────────────────────────────────────

@router.get("/stm/keys")
async def list_stm_keys(
    pattern: str = Query("conversation:*", description="Redis key pattern to scan"),
    cursor: int = Query(0, description="Scan cursor for pagination"),
    count: int = Query(100, description="Number of keys per scan"),
):
    """List all Redis keys matching pattern (STM conversations + jobs)"""
    client = await redis_client.connect()
    
    next_cursor, keys = await client.scan(cursor=cursor, match=pattern, count=count)
    
    results = []
    for key in sorted(keys):
        key_type = await client.type(key)
        ttl = await client.ttl(key)
        
        # Get size info
        if key_type == "list":
            size = await client.llen(key)
        elif key_type == "string":
            size = 1
        else:
            size = 0
        
        results.append({
            "key": key,
            "type": key_type,
            "ttl": ttl,
            "size": size,
        })
    
    return {
        "keys": results,
        "cursor": next_cursor,
        "total_returned": len(results),
        "has_more": next_cursor != 0,
    }


@router.get("/stm/keys/{key:path}")
async def get_stm_key_detail(key: str):
    """Get the content of a specific Redis key"""
    client = await redis_client.connect()
    
    exists = await client.exists(key)
    if not exists:
        raise HTTPException(status_code=404, detail=f"Key '{key}' not found")
    
    key_type = await client.type(key)
    ttl = await client.ttl(key)
    
    if key_type == "list":
        # Conversation history
        raw = await client.lrange(key, 0, -1)
        messages = []
        for item in raw:
            try:
                messages.append(json.loads(item))
            except json.JSONDecodeError:
                messages.append({"raw": item})
        return {
            "key": key,
            "type": "list",
            "ttl": ttl,
            "count": len(messages),
            "messages": messages,
        }
    elif key_type == "string":
        raw = await client.get(key)
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            data = raw
        return {
            "key": key,
            "type": "string",
            "ttl": ttl,
            "data": data,
        }
    else:
        return {
            "key": key,
            "type": key_type,
            "ttl": ttl,
            "data": f"Unsupported type: {key_type}",
        }


@router.delete("/stm/keys/{key:path}")
async def delete_stm_key(key: str):
    """Delete a specific Redis key"""
    client = await redis_client.connect()
    
    exists = await client.exists(key)
    if not exists:
        raise HTTPException(status_code=404, detail=f"Key '{key}' not found")
    
    await client.delete(key)
    return {"status": "deleted", "key": key}


@router.delete("/stm/keys")
async def delete_stm_keys_bulk(keys: List[str]):
    """Delete multiple Redis keys at once"""
    client = await redis_client.connect()
    deleted = 0
    for key in keys:
        result = await client.delete(key)
        deleted += result
    return {"status": "deleted", "deleted_count": deleted}


# ─────────────────────────────────────────────────
# Vector Memory (Weaviate) - ContactMemory collection
# ─────────────────────────────────────────────────

@router.get("/vector/collections")
async def list_vector_collections():
    """List all Weaviate collections with counts"""
    try:
        classes = await weaviate_client.get_classes()
        results = []
        for cls in classes:
            stats = await weaviate_client.get_class_stats(cls)
            results.append(stats)
        return {"collections": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vector/memories")
async def list_vector_memories(
    agent_id: Optional[str] = None,
    contact_id: Optional[str] = None,
    limit: int = Query(50, le=200),
):
    """List vector memories from ContactMemory collection with optional filters"""
    import asyncio
    try:
        def _sync_list():
            import weaviate as wv
            client = weaviate_client._ensure_connected()
            collection_name = "ContactMemory"
            
            if collection_name not in client.collections.list_all():
                return []
            
            collection = client.collections.get(collection_name)
            
            # Build filter
            filters = None
            if agent_id and contact_id:
                f1 = wv.classes.query.Filter.by_property("agent_id").equal(agent_id)
                f2 = wv.classes.query.Filter.by_property("contact_id").equal(contact_id)
                filters = f1 & f2
            elif agent_id:
                filters = wv.classes.query.Filter.by_property("agent_id").equal(agent_id)
            elif contact_id:
                filters = wv.classes.query.Filter.by_property("contact_id").equal(contact_id)
            
            results = collection.query.fetch_objects(
                limit=limit,
                filters=filters,
                include_vector=False,
            )
            
            memories = []
            for obj in results.objects:
                props = dict(obj.properties)
                memories.append({
                    "uuid": str(obj.uuid),
                    "agent_id": props.get("agent_id", ""),
                    "contact_id": props.get("contact_id", ""),
                    "content": props.get("content", ""),
                    "memory_type": props.get("memory_type", "fact"),
                    "metadata": props.get("metadata", "{}"),
                    "created_at": str(props.get("created_at", "")),
                })
            return memories
        
        memories = await asyncio.to_thread(_sync_list)
        return {"memories": memories, "count": len(memories)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vector/agent-memories")
async def list_agent_self_memories(
    agent_id: Optional[str] = None,
    memory_type: Optional[str] = None,
    limit: int = Query(50, le=200),
):
    """List agent-level self-correction memories from AgentSelfMemory collection"""
    import asyncio
    try:
        def _sync_list_agent():
            import weaviate as wv
            client = weaviate_client._ensure_connected()
            collection_name = "AgentSelfMemory"
            
            if collection_name not in client.collections.list_all():
                return []
            
            collection = client.collections.get(collection_name)
            
            # Build filter
            filters = None
            if agent_id and memory_type:
                f1 = wv.classes.query.Filter.by_property("agent_id").equal(agent_id)
                f2 = wv.classes.query.Filter.by_property("memory_type").equal(memory_type)
                filters = f1 & f2
            elif agent_id:
                filters = wv.classes.query.Filter.by_property("agent_id").equal(agent_id)
            elif memory_type:
                filters = wv.classes.query.Filter.by_property("memory_type").equal(memory_type)
            
            results = collection.query.fetch_objects(
                limit=limit,
                filters=filters,
                include_vector=False,
            )
            
            memories = []
            for obj in results.objects:
                props = dict(obj.properties)
                memories.append({
                    "uuid": str(obj.uuid),
                    "agent_id": props.get("agent_id", ""),
                    "content": props.get("content", ""),
                    "memory_type": props.get("memory_type", "correction"),
                    "metadata": props.get("metadata", "{}"),
                    "created_at": str(props.get("created_at", "")),
                })
            return memories
        
        memories = await asyncio.to_thread(_sync_list_agent)
        return {"memories": memories, "count": len(memories)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/vector/agent-memories/{uuid}")
async def delete_agent_self_memory(uuid: str):
    """Delete a specific agent self-memory by UUID"""
    import asyncio
    try:
        def _sync_delete_agent():
            client = weaviate_client._ensure_connected()
            collection = client.collections.get("AgentSelfMemory")
            collection.data.delete_by_id(uuid)
            return True
        
        await asyncio.to_thread(_sync_delete_agent)
        return {"status": "deleted", "uuid": uuid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/vector/memories/{uuid}")
async def delete_vector_memory(uuid: str):
    """Delete a specific contact vector memory by UUID"""
    import asyncio
    try:
        def _sync_delete():
            client = weaviate_client._ensure_connected()
            collection = client.collections.get("ContactMemory")
            collection.data.delete_by_id(uuid)
            return True
        
        await asyncio.to_thread(_sync_delete)
        return {"status": "deleted", "uuid": uuid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/vector/memories")
async def delete_vector_memories_bulk(uuids: List[str]):
    """Delete multiple contact vector memories by UUIDs"""
    import asyncio
    
    def _sync_bulk_delete():
        client = weaviate_client._ensure_connected()
        collection = client.collections.get("ContactMemory")
        deleted = 0
        for uid in uuids:
            try:
                collection.data.delete_by_id(uid)
                deleted += 1
            except Exception:
                pass
        return deleted
    
    deleted = await asyncio.to_thread(_sync_bulk_delete)
    return {"status": "deleted", "deleted_count": deleted}


@router.delete("/vector/memories/contact/{contact_id}")
async def delete_all_memories_for_contact(contact_id: str, agent_id: Optional[str] = None):
    """Delete ALL vector memories for a specific contact (optionally filtered by agent)"""
    import asyncio
    import weaviate as wv
    
    def _sync_purge():
        client = weaviate_client._ensure_connected()
        collection_name = "ContactMemory"
        
        if collection_name not in client.collections.list_all():
            return 0
        
        collection = client.collections.get(collection_name)
        
        f_contact = wv.classes.query.Filter.by_property("contact_id").equal(contact_id)
        if agent_id:
            f_agent = wv.classes.query.Filter.by_property("agent_id").equal(agent_id)
            combined = f_contact & f_agent
        else:
            combined = f_contact
        
        result = collection.data.delete_many(where=combined)
        return result.successful if hasattr(result, 'successful') else 0
    
    deleted = await asyncio.to_thread(_sync_purge)
    return {"status": "purged", "contact_id": contact_id, "deleted_count": deleted}


# ─────────────────────────────────────────────────
# MTM (PostgreSQL) - Medium-Term Memory
# ─────────────────────────────────────────────────

@router.get("/mtm/sessions")
async def list_mtm_sessions(
    agent_id: Optional[str] = None,
    limit: int = Query(100, le=500),
):
    """List all MTM sessions with message counts and last interaction"""
    from app.database import AsyncSessionLocal
    from app.models.conversation_message import ConversationMessage
    from sqlalchemy import select, func, desc
    import uuid

    async with AsyncSessionLocal() as db:
        q = (
            select(
                ConversationMessage.agent_id,
                ConversationMessage.session_id,
                func.count().label("total_messages"),
                func.max(ConversationMessage.created_at).label("last_interaction"),
                func.min(ConversationMessage.created_at).label("first_interaction"),
            )
            .group_by(ConversationMessage.agent_id, ConversationMessage.session_id)
            .order_by(desc(func.max(ConversationMessage.created_at)))
            .limit(limit)
        )

        if agent_id:
            q = q.where(ConversationMessage.agent_id == uuid.UUID(agent_id))

        result = await db.execute(q)
        rows = result.all()

        sessions = []
        for row in rows:
            sessions.append({
                "agent_id": str(row.agent_id),
                "session_id": row.session_id,
                "total_messages": row.total_messages,
                "last_interaction": row.last_interaction.isoformat() if row.last_interaction else None,
                "first_interaction": row.first_interaction.isoformat() if row.first_interaction else None,
            })

        return {"sessions": sessions, "count": len(sessions)}


@router.get("/mtm/sessions/{session_id}")
async def get_mtm_session_messages(
    session_id: str,
    agent_id: Optional[str] = None,
    limit: int = Query(200, le=1000),
):
    """Get all messages for a specific MTM session"""
    from app.database import AsyncSessionLocal
    from app.models.conversation_message import ConversationMessage
    from sqlalchemy import select
    import uuid

    async with AsyncSessionLocal() as db:
        q = (
            select(ConversationMessage)
            .where(ConversationMessage.session_id == session_id)
            .order_by(ConversationMessage.created_at.asc())
            .limit(limit)
        )

        if agent_id:
            q = q.where(ConversationMessage.agent_id == uuid.UUID(agent_id))

        result = await db.execute(q)
        rows = result.scalars().all()

        messages = []
        for r in rows:
            messages.append({
                "id": str(r.id),
                "agent_id": str(r.agent_id),
                "session_id": r.session_id,
                "role": r.role,
                "content": r.content,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })

        return {
            "session_id": session_id,
            "messages": messages,
            "count": len(messages),
        }


@router.delete("/mtm/sessions/{session_id}")
async def delete_mtm_session(session_id: str, agent_id: Optional[str] = None):
    """Delete all messages for a specific MTM session"""
    from app.database import AsyncSessionLocal
    from app.models.conversation_message import ConversationMessage
    from sqlalchemy import delete as sa_delete
    import uuid

    async with AsyncSessionLocal() as db:
        q = sa_delete(ConversationMessage).where(
            ConversationMessage.session_id == session_id
        )
        if agent_id:
            q = q.where(ConversationMessage.agent_id == uuid.UUID(agent_id))

        result = await db.execute(q)
        await db.commit()
        return {"status": "deleted", "session_id": session_id, "deleted_count": result.rowcount}


@router.delete("/mtm/messages")
async def delete_mtm_messages_bulk(ids: List[str]):
    """Delete multiple MTM messages by IDs"""
    from app.database import AsyncSessionLocal
    from app.models.conversation_message import ConversationMessage
    from sqlalchemy import delete as sa_delete
    import uuid

    async with AsyncSessionLocal() as db:
        uuids = [uuid.UUID(i) for i in ids]
        q = sa_delete(ConversationMessage).where(
            ConversationMessage.id.in_(uuids)
        )
        result = await db.execute(q)
        await db.commit()
        return {"status": "deleted", "deleted_count": result.rowcount}
