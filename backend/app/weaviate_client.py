"""
Weaviate Client for vector database operations
Async-safe wrapper using asyncio.to_thread to prevent event loop blocking
"""
import asyncio
import threading
import weaviate
from weaviate.classes.init import Auth
from typing import Optional, List, Dict, Any
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
                    parsed = urlparse(settings.WEAVIATE_URL)
                    self.client = weaviate.connect_to_custom(
                        http_host=parsed.hostname,
                        http_port=parsed.port or 8080,
                        http_secure=parsed.scheme == "https",
                        grpc_host=parsed.hostname,
                        grpc_port=50051,
                        grpc_secure=False
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
            return await asyncio.to_thread(self._sync_is_ready)
        except Exception:
            return False
    
    async def get_classes(self) -> List[str]:
        """Get all collection names (async-safe)"""
        try:
            return await asyncio.to_thread(self._sync_get_classes)
        except Exception:
            return []
    
    async def get_class_stats(self, class_name: str) -> Dict[str, Any]:
        """Get statistics for a collection (async-safe)"""
        try:
            return await asyncio.to_thread(self._sync_get_class_stats, class_name)
        except Exception as e:
            return {"name": class_name, "error": str(e)}
    
    async def search(
        self,
        class_name: str,
        query: str,
        limit: int = 5,
        properties: List[str] = None
    ) -> List[Dict[str, Any]]:
        """Perform vector search (async-safe)"""
        try:
            return await asyncio.to_thread(
                self._sync_search, class_name, query, limit, properties
            )
        except Exception as e:
            return [{"error": str(e)}]
    
    async def purge_class(self, class_name: str) -> bool:
        """Delete all objects in a collection (async-safe)"""
        try:
            return await asyncio.to_thread(self._sync_purge_class, class_name)
        except Exception:
            return False
    
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
        properties: List[str] = None
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


# Global instance
weaviate_client = WeaviateClient()


def get_weaviate() -> WeaviateClient:
    """Dependency for getting Weaviate client"""
    return weaviate_client
