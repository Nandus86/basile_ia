"""
Weaviate Client for vector database operations
Async-safe wrapper using asyncio.to_thread to prevent event loop blocking
"""
import asyncio
import threading
import weaviate
from weaviate.classes.init import Auth
from typing import Optional, List, Dict, Any, Union
from urllib.parse import urlparse

from app.config import settings


class WeaviateClient:
    """Async-safe Weaviate client wrapper.
    
    All Weaviate SDK calls are synchronous, so we run them in a thread
    to avoid blocking the FastAPI async event loop.
    """
    
    def __init__(self):
        self.client: Optional[weaviate.WeaviateClient] = None
        self._lock = threading.Lock()
    
    def _ensure_connected(self) -> weaviate.WeaviateClient:
        """Initialize Weaviate connection (thread-safe)"""
        if not self.client:
            with self._lock:
                if not self.client:  # Double-check after lock
                    import os
                    parsed = urlparse(settings.WEAVIATE_URL)
                    headers = {}
                    openai_key = os.environ.get("OPENAI_API_KEY", "")
                    if openai_key:
                        headers["X-Openai-Api-Key"] = openai_key
                    
                    # Auth: use API key from env if provided (for Weaviate Cloud)
                    auth_credentials = None
                    if settings.WEAVIATE_API_KEY:
                        auth_credentials = Auth.api_key(settings.WEAVIATE_API_KEY)
                    
                    grpc_port = settings.WEAVIATE_GRPC_PORT or 50051
                    is_secure = parsed.scheme == "https"
                    
                    self.client = weaviate.connect_to_custom(
                        http_host=parsed.hostname,
                        http_port=parsed.port or 8080,
                        http_secure=is_secure,
                        grpc_host=parsed.hostname,
                        grpc_port=grpc_port,
                        grpc_secure=is_secure,
                        headers=headers,
                        auth_credentials=auth_credentials
                    )
        return self.client
    
    def disconnect(self):
        """Close Weaviate connection"""
        if self.client:
            self.client.close()
            self.client = None
    
    # ==================== Async Public API ====================
    
    async def is_ready(self) -> bool:
        """Check if Weaviate is ready (async-safe)"""
        try:
            return await asyncio.to_thread(self._sync_is_ready) # type: ignore
        except Exception:
            return False
    
    async def get_classes(self) -> List[str]:
        """Get all collection names (async-safe)"""
        try:
            return await asyncio.to_thread(self._sync_get_classes) # type: ignore
        except Exception:
            return []
    
    async def get_class_stats(self, class_name: str) -> Dict[str, Any]:
        """Get statistics for a collection (async-safe)"""
        try:
            return await asyncio.to_thread(self._sync_get_class_stats, class_name) # type: ignore
        except Exception as e:
            return {"name": class_name, "error": str(e)}
    
    async def search(
        self,
        class_name: str,
        query: str,
        limit: int = 5,
        properties: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Perform vector search (async-safe)"""
        try:
            return await asyncio.to_thread( # type: ignore
                self._sync_search, class_name, query, limit, properties
            )
        except Exception as e:
            return [{"error": str(e)}]
    
    async def purge_class(self, class_name: str) -> bool:
        """Delete all objects in a collection (async-safe)"""
        try:
            return await asyncio.to_thread(self._sync_purge_class, class_name) # type: ignore
        except Exception:
            return False
            
    async def save_contact_memory(
        self,
        agent_id: str,
        contact_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        memory_type: str = "fact"
    ) -> bool:
        """Save a new qualitative memory for a contact (async-safe)"""
        try:
            return await asyncio.to_thread( # type: ignore
                self._sync_save_contact_memory, agent_id, contact_id, content, metadata, memory_type
            )
        except Exception as e:
            print(f"Error saving contact memory: {e}")
            return False

    async def search_contact_memories(
        self,
        agent_id: str,
        contact_id: str,
        query: str,
        limit: int = 5,
        memory_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search historical memories for a specific contact (async-safe)"""
        try:
            return await asyncio.to_thread( # type: ignore
                self._sync_search_contact_memories, agent_id, contact_id, query, limit, memory_type
            )
        except Exception as e:
            print(f"Error searching contact memories: {e}")
            return []

    async def save_agent_self_memory(
        self,
        agent_id: str,
        content: str,
        memory_type: str = "self_correction",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Save an agent-level learning/correction memory (async-safe)"""
        try:
            return await asyncio.to_thread( # type: ignore
                self._sync_save_agent_self_memory, agent_id, content, memory_type, metadata
            )
        except Exception as e:
            print(f"Error saving agent self memory: {e}")
            return False

    async def search_agent_self_memories(
        self,
        agent_id: str,
        query: str,
        limit: int = 5,
        memory_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search agent-level learning memories (async-safe)"""
        try:
            return await asyncio.to_thread( # type: ignore
                self._sync_search_agent_self_memories, agent_id, query, limit, memory_type
            )
        except Exception as e:
            print(f"Error searching agent self memories: {e}")
            return []

    async def save_information_base_node(
        self,
        base_code: str,
        user_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        external_id: Optional[str] = None,
        facet_index: Optional[int] = None,
        facet_type: Optional[str] = None
    ) -> bool:
        """Save a new node into a generic Information Base collection (async-safe)"""
        try:
            return await asyncio.to_thread( # type: ignore
                self._sync_save_information_base_node, base_code, user_id, content, metadata, external_id, facet_index, facet_type
            )
        except Exception as e:
            print(f"Error saving information base node: {e}")
            return False

    async def delete_information_base_nodes(
        self,
        base_code: str,
        user_id: str,
        external_id: Optional[str] = None
    ) -> bool:
        """Delete all nodes (or a specific node) for a specific Information Base and user ID (async-safe)"""
        try:
            return await asyncio.to_thread( # type: ignore
                self._sync_delete_information_base_nodes, base_code, user_id, external_id
            )
        except Exception as e:
            print(f"Error deleting information base nodes: {e}")
            return False

    async def search_information_bases(
        self,
        base_codes: List[str],
        user_id: str,
        query: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Search specific Information Bases for a user (async-safe)"""
        try:
            return await asyncio.to_thread( # type: ignore
                self._sync_search_information_bases, base_codes, user_id, query, limit
            )
        except Exception as e:
            print(f"Error searching information bases: {e}")
            return []
    
    # ==================== Sync Internals (run in thread) ====================
    
    def _sync_is_ready(self) -> bool:
        client = self._ensure_connected()
        return client.is_ready()
    
    def _sync_get_classes(self) -> List[str]:
        client = self._ensure_connected()
        collections = client.collections.list_all()
        return list(collections.keys())
    
    def _sync_get_class_stats(self, class_name: str) -> Dict[str, Any]:
        client = self._ensure_connected()
        collection = client.collections.get(class_name)
        count = collection.aggregate.over_all(total_count=True).total_count
        return {"name": class_name, "count": count}
    
    def _sync_search(
        self,
        class_name: str,
        query: str,
        limit: int = 5,
        properties: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        client = self._ensure_connected()
        collection = client.collections.get(class_name)
        
        results = collection.query.near_text(
            query=query,
            limit=limit,
            return_properties=properties
        )
        
        return [
            {
                "properties": dict(obj.properties),
                "distance": obj.metadata.distance if obj.metadata else None
            }
            for obj in results.objects
        ]
    
    def _sync_purge_class(self, class_name: str) -> bool:
        client = self._ensure_connected()
        client.collections.delete(class_name)
        return True

    def _sync_save_contact_memory(
        self,
        agent_id: str,
        contact_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        memory_type: str = "fact"
    ) -> bool:
        client = self._ensure_connected()
        collection_name = "ContactMemory"
        
        # Ensure collection exists (lazy creation)
        if collection_name not in client.collections.list_all():
            client.collections.create(
                name=collection_name,
                description="Intelligent Vector Memory for Agent Contacts",
                vectorizer_config=weaviate.classes.config.Configure.Vectorizer.text2vec_openai(),
                properties=[
                    weaviate.classes.config.Property(name="agent_id", data_type=weaviate.classes.config.DataType.TEXT, skip_vectorization=True),
                    weaviate.classes.config.Property(name="contact_id", data_type=weaviate.classes.config.DataType.TEXT, skip_vectorization=True),
                    weaviate.classes.config.Property(name="content", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="metadata", data_type=weaviate.classes.config.DataType.TEXT, skip_vectorization=True),
                    weaviate.classes.config.Property(name="memory_type", data_type=weaviate.classes.config.DataType.TEXT, skip_vectorization=True),
                    weaviate.classes.config.Property(name="created_at", data_type=weaviate.classes.config.DataType.DATE, skip_vectorization=True),
                ]
            )
            
        collection = client.collections.get(collection_name)
        
        import json
        from datetime import datetime, timezone
        
        props = {
            "agent_id": str(agent_id),
            "contact_id": str(contact_id),
            "content": content,
            "metadata": json.dumps(metadata) if metadata else "{}",
            "memory_type": memory_type,
            "created_at": datetime.now(timezone.utc)
        }
        
        collection.data.insert(properties=props)
        return True

    def _sync_search_contact_memories(
        self,
        agent_id: str,
        contact_id: str,
        query: str,
        limit: int = 5,
        memory_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        client = self._ensure_connected()
        collection_name = "ContactMemory"
        
        if collection_name not in client.collections.list_all():
            return []
            
        collection = client.collections.get(collection_name)
        
        # Filter by agent and contact
        filter_agent = weaviate.classes.query.Filter.by_property("agent_id").equal(str(agent_id))
        filter_contact = weaviate.classes.query.Filter.by_property("contact_id").equal(str(contact_id))
        combined_filter = filter_agent & filter_contact
        
        # Optionally filter by memory_type
        if memory_type:
            filter_type = weaviate.classes.query.Filter.by_property("memory_type").equal(memory_type)
            combined_filter = combined_filter & filter_type
        
        results = collection.query.near_text(
            query=query,
            limit=limit,
            filters=combined_filter
        )
        
        memories = []
        for obj in results.objects:
            props = dict(obj.properties)
            memories.append({
                "content": props.get("content", ""),
                "metadata": props.get("metadata", "{}"),
                "memory_type": props.get("memory_type", "fact"),
                "created_at": props.get("created_at"),
                "distance": obj.metadata.distance if obj.metadata else None
            })
            
        return memories

    # ==================== Agent Self-Memory (agent-level learning) ====================

    def _sync_save_agent_self_memory(
        self,
        agent_id: str,
        content: str,
        memory_type: str = "self_correction",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Save an agent-level learning/correction memory."""
        client = self._ensure_connected()
        collection_name = "AgentSelfMemory"
        
        if collection_name not in client.collections.list_all():
            client.collections.create(
                name=collection_name,
                description="Agent-level self-correction and learning memory",
                vectorizer_config=weaviate.classes.config.Configure.Vectorizer.text2vec_openai(),
                properties=[
                    weaviate.classes.config.Property(name="agent_id", data_type=weaviate.classes.config.DataType.TEXT, skip_vectorization=True),
                    weaviate.classes.config.Property(name="content", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="memory_type", data_type=weaviate.classes.config.DataType.TEXT, skip_vectorization=True),
                    weaviate.classes.config.Property(name="metadata", data_type=weaviate.classes.config.DataType.TEXT, skip_vectorization=True),
                    weaviate.classes.config.Property(name="created_at", data_type=weaviate.classes.config.DataType.DATE, skip_vectorization=True),
                ]
            )
        
        collection = client.collections.get(collection_name)
        
        import json
        from datetime import datetime, timezone
        
        props = {
            "agent_id": str(agent_id),
            "content": content,
            "memory_type": memory_type,
            "metadata": json.dumps(metadata) if metadata else "{}",
            "created_at": datetime.now(timezone.utc)
        }
        
        collection.data.insert(properties=props)
        return True

    def _sync_search_agent_self_memories(
        self,
        agent_id: str,
        query: str,
        limit: int = 5,
        memory_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search agent-level learning memories."""
        client = self._ensure_connected()
        collection_name = "AgentSelfMemory"
        
        if collection_name not in client.collections.list_all():
            return []
            
        collection = client.collections.get(collection_name)
        
        combined_filter = weaviate.classes.query.Filter.by_property("agent_id").equal(str(agent_id))
        
        if memory_type:
            filter_type = weaviate.classes.query.Filter.by_property("memory_type").equal(memory_type)
            combined_filter = combined_filter & filter_type
        
        results = collection.query.near_text(
            query=query,
            limit=limit,
            filters=combined_filter
        )
        
        memories = []
        for obj in results.objects:
            props = dict(obj.properties)
            memories.append({
                "content": props.get("content", ""),
                "memory_type": props.get("memory_type", "self_correction"),
                "metadata": props.get("metadata", "{}"),
                "created_at": props.get("created_at"),
                "distance": obj.metadata.distance if obj.metadata else None
            })
            
        return memories

    def _sync_save_information_base_node(
        self,
        base_code: str,
        user_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        external_id: Optional[str] = None,
        facet_index: Optional[int] = None,
        facet_type: Optional[str] = None
    ) -> bool:
        client = self._ensure_connected()
        collection_name = "InformationBaseNode"
        
        # Ensure collection exists (lazy creation with vectorizer)
        if collection_name not in client.collections.list_all():
            client.collections.create(
                name=collection_name,
                description="Custom user-defined Information Bases",
                vectorizer_config=weaviate.classes.config.Configure.Vectorizer.text2vec_openai(),
                properties=[
                    weaviate.classes.config.Property(name="base_code", data_type=weaviate.classes.config.DataType.TEXT, skip_vectorization=True),
                    weaviate.classes.config.Property(name="user_id", data_type=weaviate.classes.config.DataType.TEXT, skip_vectorization=True),
                    weaviate.classes.config.Property(name="content", data_type=weaviate.classes.config.DataType.TEXT),
                    weaviate.classes.config.Property(name="metadata", data_type=weaviate.classes.config.DataType.TEXT, skip_vectorization=True),
                    weaviate.classes.config.Property(name="created_at", data_type=weaviate.classes.config.DataType.DATE, skip_vectorization=True),
                    weaviate.classes.config.Property(name="external_id", data_type=weaviate.classes.config.DataType.TEXT, skip_vectorization=True),
                    weaviate.classes.config.Property(name="facet_type", data_type=weaviate.classes.config.DataType.TEXT, skip_vectorization=True),
                ]
            )
        else:
            # Ensure new properties exist on existing collection (schema evolution)
            try:
                collection_obj = client.collections.get(collection_name)
                existing_props = {p.name for p in collection_obj.config.get().properties}
                new_props = [
                    ("external_id", weaviate.classes.config.DataType.TEXT),
                    ("facet_type", weaviate.classes.config.DataType.TEXT),
                ]
                for prop_name, prop_type in new_props:
                    if prop_name not in existing_props:
                        collection_obj.config.add_property(
                            weaviate.classes.config.Property(
                                name=prop_name,
                                data_type=prop_type,
                                skip_vectorization=True
                            )
                        )
            except Exception:
                pass  # Non-critical: properties may already exist
            
        collection = client.collections.get(collection_name)
        
        import json
        import uuid
        from datetime import datetime, timezone
        
        props = {
            "base_code": str(base_code),
            "user_id": str(user_id),
            "content": content,
            "metadata": json.dumps(metadata) if metadata else "{}",
            "created_at": datetime.now(timezone.utc),
        }
        
        # Add new fields if available
        if external_id:
            props["external_id"] = str(external_id)
        if facet_type:
            props["facet_type"] = facet_type
        
        obj_uuid = None
        if external_id:
            # Compose UUID with facet_index for multi-facet records
            facet_suffix = f"_f{facet_index}" if facet_index is not None else ""
            obj_str = f"{base_code}_{user_id}_{external_id}{facet_suffix}"
            obj_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, obj_str))
            
            if collection.data.exists(obj_uuid):
                collection.data.delete_by_id(obj_uuid)
                
        if obj_uuid:
            collection.data.insert(properties=props, uuid=obj_uuid)
        else:
            collection.data.insert(properties=props)
            
        return True

    def _sync_delete_information_base_nodes(
        self,
        base_code: str,
        user_id: str,
        external_id: Optional[str] = None
    ) -> bool:
        client = self._ensure_connected()
        collection_name = "InformationBaseNode"
        
        if collection_name not in client.collections.list_all():
            return True
            
        collection = client.collections.get(collection_name)
        
        if external_id:
            # Delete ALL facets for this external_id using property filter
            # This handles multi-facet records (summary + field chunks)
            filter_user = weaviate.classes.query.Filter.by_property("user_id").equal(str(user_id))
            filter_code = weaviate.classes.query.Filter.by_property("base_code").equal(str(base_code))
            filter_ext = weaviate.classes.query.Filter.by_property("external_id").equal(str(external_id))
            combined_filter = filter_user & filter_code & filter_ext
            collection.data.delete_many(where=combined_filter)
            
            # Also try legacy single-UUID delete for backward compat (old records without external_id property)
            try:
                import uuid
                obj_str = f"{base_code}_{user_id}_{external_id}"
                obj_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, obj_str))
                if collection.data.exists(obj_uuid):
                    collection.data.delete_by_id(obj_uuid)
            except Exception:
                pass
        else:
            filter_user = weaviate.classes.query.Filter.by_property("user_id").equal(str(user_id))
            filter_code = weaviate.classes.query.Filter.by_property("base_code").equal(str(base_code))
            combined_filter = filter_user & filter_code
            collection.data.delete_many(where=combined_filter)
            
        return True

    def _sync_search_information_bases(
        self,
        base_codes: List[str],
        user_id: str,
        query: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        if not base_codes:
            return []
            
        client = self._ensure_connected()
        collection_name = "InformationBaseNode"
        
        if collection_name not in client.collections.list_all():
            return []
            
        collection = client.collections.get(collection_name)
        
        filter_user = weaviate.classes.query.Filter.by_property("user_id").equal(str(user_id))
        
        # Filter by multiple base codes
        code_filters = []
        for code in base_codes:
            code_filters.append(weaviate.classes.query.Filter.by_property("base_code").equal(str(code)))
        
        combined_code_filter = code_filters[0]
        for cf in code_filters[1:]:
            combined_code_filter = combined_code_filter | cf
            
        combined_filter = filter_user & combined_code_filter
        
        results = collection.query.near_text(
            query=query,
            limit=limit,
            filters=combined_filter
        )
        
        Nodes = []
        for obj in results.objects:
            props = dict(obj.properties)
            Nodes.append({
                "base_code": props.get("base_code", ""),
                "content": props.get("content", ""),
                "metadata": props.get("metadata", "{}"),
                "facet_type": props.get("facet_type", "raw"),
                "distance": obj.metadata.distance if obj.metadata else None
            })
            
        return Nodes


# Global instance
weaviate_client = WeaviateClient()


def get_weaviate() -> WeaviateClient:
    """Dependency for getting Weaviate client"""
    return weaviate_client
