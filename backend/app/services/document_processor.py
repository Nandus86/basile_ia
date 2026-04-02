"""
Document Processor Service
Handles chunking, embedding, and indexing of documents into Weaviate
Uses OpenAI API for embeddings (text-embedding-3-small)
"""
import os
import hashlib
import asyncio
from typing import List, Dict, Any, Optional
from pathlib import Path
import logging
from uuid import UUID
import httpx

from langchain_text_splitters import RecursiveCharacterTextSplitter
import weaviate
from weaviate.classes.config import Configure, Property, DataType

from app.config import settings
from app.weaviate_client import get_weaviate

logger = logging.getLogger(__name__)


# Storage directory for uploaded files
UPLOAD_DIR = Path("/app/uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


class OpenAIEmbeddings:
    """
    Embeddings using OpenAI API.
    Model: text-embedding-3-small (1536 dimensions, cheaper and fast)
    """
    
    def __init__(self, model: str = "text-embedding-3-small"):
        self.model_name = model
        self.dimension = 1536  # text-embedding-3-small produces 1536-dimensional vectors
        self.api_key = settings.OPENAI_API_KEY
    
    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts via OpenAI API"""
        embeddings = []
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Process in batches of 100 (OpenAI limit is 2048)
            batch_size = 100
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                try:
                    response = await client.post(
                        "https://api.openai.com/v1/embeddings",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": self.model_name,
                            "input": batch
                        }
                    )
                    response.raise_for_status()
                    result = response.json()
                    
                    # Sort by index to maintain order
                    sorted_data = sorted(result["data"], key=lambda x: x["index"])
                    batch_embeddings = [item["embedding"] for item in sorted_data]
                    embeddings.extend(batch_embeddings)
                    
                except Exception as e:
                    logger.error(f"Error generating OpenAI embedding: {e}")
                    # Return zero vectors on error for this batch
                    embeddings.extend([[0.0] * self.dimension] * len(batch))
        
        return embeddings
    
    async def embed_query(self, text: str) -> List[float]:
        """Generate embedding for a single query"""
        results = await self.embed_documents([text])
        return results[0] if results else [0.0] * self.dimension


class DocumentProcessor:
    """Processes documents for vector search using OpenAI embeddings"""
    
    WEAVIATE_CLASS = "AgentDocuments"
    
    def __init__(self):
        self.embeddings = OpenAIEmbeddings()
        self.weaviate = get_weaviate()
    
    async def ensure_collection_exists(self):
        """Create Weaviate collection if it doesn't exist"""
        await asyncio.to_thread(self._sync_ensure_collection_exists)
    
    def _sync_ensure_collection_exists(self):
        """Sync implementation for collection creation"""
        try:
            client = self.weaviate._ensure_connected()
            
            if not client.collections.exists(self.WEAVIATE_CLASS):
                client.collections.create(
                    name=self.WEAVIATE_CLASS,
                    vectorizer_config=Configure.Vectorizer.none(),
                    properties=[
                        Property(name="content", data_type=DataType.TEXT),
                        Property(name="document_id", data_type=DataType.TEXT),
                        Property(name="document_name", data_type=DataType.TEXT),
                        Property(name="chunk_index", data_type=DataType.INT),
                        Property(name="source", data_type=DataType.TEXT),
                        Property(name="chunk_metadata", data_type=DataType.TEXT),
                    ]
                )
                logger.info(f"Created Weaviate collection: {self.WEAVIATE_CLASS}")
            
        except Exception as e:
            logger.error(f"Error creating Weaviate collection: {e}")
            raise
    
    def calculate_hash(self, content: str) -> str:
        """Calculate SHA-256 hash of content"""
        return hashlib.sha256(content.encode()).hexdigest()
    
    async def read_file_content(self, file_path: str, file_type: str) -> str:
        """Read content from file based on type"""
        content = ""
        
        try:
            if file_type in ["txt", "markdown", "md"]:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    
            elif file_type == "pdf":
                # Use pypdf for PDF reading
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(file_path)
                    content = "\n".join(page.extract_text() for page in reader.pages)
                except ImportError:
                    logger.warning("pypdf not installed, trying alternative")
                    with open(file_path, "rb") as f:
                        content = f"[PDF file - install pypdf for text extraction]"
                        
            elif file_type == "docx":
                try:
                    from docx import Document
                    doc = Document(file_path)
                    content = "\n".join(para.text for para in doc.paragraphs)
                except ImportError:
                    content = "[DOCX file - install python-docx for text extraction]"
                    
            elif file_type == "html":
                try:
                    from bs4 import BeautifulSoup
                    with open(file_path, "r", encoding="utf-8") as f:
                        soup = BeautifulSoup(f.read(), "html.parser")
                        content = soup.get_text(separator="\n")
                except ImportError:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        
            elif file_type == "json":
                import json
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    content = json.dumps(data, indent=2, ensure_ascii=False)
                    
            elif file_type == "csv":
                import csv
                with open(file_path, "r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    rows = list(reader)
                    content = "\n".join([", ".join(row) for row in rows])
            else:
                # Try as text
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            raise
        
        return content
    
    def chunk_text(
        self,
        text: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ) -> List[str]:
        """Split text into chunks.
        
        Primary: SemanticChunker (splits by meaning/context boundaries)
        Fallback: RecursiveCharacterTextSplitter (splits by character count)
        """
        # Try SemanticChunker first for context-aware splitting
        if len(text) > 500:  # Only worth it for non-trivial texts
            try:
                from langchain_experimental.text_splitter import SemanticChunker
                from langchain_openai import OpenAIEmbeddings
                
                sem_chunker = SemanticChunker(
                    OpenAIEmbeddings(model="text-embedding-3-small"),
                    breakpoint_threshold_type="percentile",
                    breakpoint_threshold_amount=85,
                )
                docs = sem_chunker.create_documents([text])
                chunks = [doc.page_content for doc in docs if doc.page_content.strip()]
                
                if chunks:
                    logger.info(
                        f"SemanticChunker: {len(chunks)} context-aware chunks "
                        f"(vs ~{max(1, len(text)//chunk_size)} by chars)"
                    )
                    return chunks
            except Exception as e:
                logger.warning(f"SemanticChunker failed, falling back to char-based: {e}")
        
        # Fallback: RecursiveCharacterTextSplitter (original behavior)
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        return splitter.split_text(text)
    
    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for texts using local transformers server"""
        # Process in batches to avoid overwhelming the server
        batch_size = 50
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = await self.embeddings.embed_documents(batch)
            all_embeddings.extend(embeddings)
            logger.info(f"Generated embeddings for batch {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1}")
            
        return all_embeddings
    
    async def index_chunks(
        self,
        chunks: List[str],
        embeddings: List[List[float]],
        document_id: str,
        document_name: str,
        source: str,
        metadata: Dict[str, Any] = None
    ) -> int:
        """Index chunks into Weaviate (async-safe)"""
        await self.ensure_collection_exists()
        return await asyncio.to_thread(
            self._sync_index_chunks,
            chunks, embeddings, document_id, document_name, source, metadata
        )
    
    def _sync_index_chunks(
        self,
        chunks: List[str],
        embeddings: List[List[float]],
        document_id: str,
        document_name: str,
        source: str,
        metadata: Dict[str, Any] = None
    ) -> int:
        """Sync implementation for chunk indexing"""
        import json
        
        client = self.weaviate._ensure_connected()
        collection = client.collections.get(self.WEAVIATE_CLASS)
        metadata_str = json.dumps(metadata or {})
        
        with collection.batch.fixed_size(batch_size=100) as batch:
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                batch.add_object(
                    properties={
                        "content": chunk,
                        "document_id": document_id,
                        "document_name": document_name,
                        "chunk_index": i,
                        "source": source,
                        "chunk_metadata": metadata_str
                    },
                    vector=embedding
                )
        
        logger.info(f"Indexed {len(chunks)} chunks for document {document_name}")
        return len(chunks)
    
    async def process_document(
        self,
        document_id: str,
        file_path: str,
        file_type: str,
        document_name: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Full document processing pipeline"""
        try:
            logger.info(f"Processing document: {document_name}")
            
            # 1. Read content
            content = await self.read_file_content(file_path, file_type)
            content_hash = self.calculate_hash(content)
            logger.info(f"Read {len(content)} characters from {document_name}")
            
            # 2. Chunk
            chunks = self.chunk_text(content, chunk_size, chunk_overlap)
            logger.info(f"Created {len(chunks)} chunks")
            
            if not chunks:
                return {
                    "success": False,
                    "error": "No content to process",
                    "chunk_count": 0
                }
            
            # 3. Generate embeddings using OpenAI
            logger.info(f"Generating embeddings using OpenAI API...")
            embeddings = await self.generate_embeddings(chunks)
            
            # 4. Index in Weaviate
            chunk_count = await self.index_chunks(
                chunks=chunks,
                embeddings=embeddings,
                document_id=document_id,
                document_name=document_name,
                source=file_path,
                metadata=metadata
            )
            
            logger.info(f"Successfully processed document: {document_name}")
            
            return {
                "success": True,
                "chunk_count": chunk_count,
                "content_hash": content_hash,
                "content_length": len(content),
                "embedding_model": self.embeddings.model_name
            }
            
        except Exception as e:
            logger.error(f"Document processing error: {e}")
            return {
                "success": False,
                "error": str(e),
                "chunk_count": 0
            }
    
    async def delete_document_chunks(self, document_id: str) -> bool:
        """Delete all chunks for a document (async-safe)"""
        try:
            return await asyncio.to_thread(self._sync_delete_document_chunks, document_id)
        except Exception as e:
            logger.error(f"Error deleting chunks: {e}")
            return False
    
    def _sync_delete_document_chunks(self, document_id: str) -> bool:
        """Sync implementation for chunk deletion"""
        client = self.weaviate._ensure_connected()
        collection = client.collections.get(self.WEAVIATE_CLASS)
        
        collection.data.delete_many(
            where=weaviate.classes.query.Filter.by_property("document_id").equal(document_id)
        )
        
        logger.info(f"Deleted chunks for document {document_id}")
        return True
    
    async def search(
        self,
        query: str,
        limit: int = 5,
        document_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar chunks using local transformers embeddings (async-safe)"""
        try:
            # Generate query embedding using local transformers (already async)
            query_embedding = await self.embeddings.embed_query(query)
            
            # Run the sync Weaviate search in a thread
            return await asyncio.to_thread(
                self._sync_search, query_embedding, limit, document_ids
            )
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []
    
    def _sync_search(
        self,
        query_embedding: List[float],
        limit: int = 5,
        document_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Sync implementation for vector search"""
        import json
        
        client = self.weaviate._ensure_connected()
        collection = client.collections.get(self.WEAVIATE_CLASS)
        
        if document_ids:
            from weaviate.classes.query import Filter
            filters = Filter.by_property("document_id").contains_any(document_ids)
            results = collection.query.near_vector(
                near_vector=query_embedding,
                limit=limit,
                filters=filters,
                return_properties=["content", "document_id", "document_name", "chunk_index", "chunk_metadata"]
            )
        else:
            results = collection.query.near_vector(
                near_vector=query_embedding,
                limit=limit,
                return_properties=["content", "document_id", "document_name", "chunk_index", "chunk_metadata"]
            )
        
        return [
            {
                "document_id": obj.properties.get("document_id"),
                "document_name": obj.properties.get("document_name"),
                "chunk_index": obj.properties.get("chunk_index"),
                "content": obj.properties.get("content"),
                "score": 1 - (obj.metadata.distance or 0) if obj.metadata else 1.0,
                "metadata": json.loads(obj.properties.get("chunk_metadata", "{}"))
            }
            for obj in results.objects
        ]


# Global instance
document_processor = DocumentProcessor()


def get_document_processor() -> DocumentProcessor:
    """Get document processor instance"""
    return document_processor
