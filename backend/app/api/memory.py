"""
Memory Management API — View and delete STM (Redis) and Vector Memory (Weaviate) entries
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
import json

from app.redis_client import redis_client
from app.weaviate_client import weaviate_client

router = APIRouter()


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
                    "metadata": props.get("metadata", "{}"),
                    "created_at": str(props.get("created_at", "")),
                })
            return memories
        
        memories = await asyncio.to_thread(_sync_list)
        return {"memories": memories, "count": len(memories)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/vector/memories/{uuid}")
async def delete_vector_memory(uuid: str):
    """Delete a specific vector memory by UUID"""
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
    """Delete multiple vector memories by UUIDs"""
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
