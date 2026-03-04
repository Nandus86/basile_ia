"""
RAG Service - Retrieval Augmented Generation
Provides context from documents to agents
"""
import asyncio
from typing import List, Dict, Any, Optional
from uuid import UUID
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.agent import Agent
from app.models.document import Document
from app.services.document_processor import get_document_processor

logger = logging.getLogger(__name__)


class RAGService:
    """Service for augmenting agent responses with document context"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.processor = get_document_processor()
    
    async def get_agent_documents(self, agent_id: str) -> List[Document]:
        """Get all active documents for an agent"""
        result = await self.db.execute(
            select(Agent)
            .options(selectinload(Agent.documents))
            .where(Agent.id == UUID(agent_id))
        )
        agent = result.scalar_one_or_none()
        
        if not agent:
            return []
        
        # Get agent-specific documents
        documents = [doc for doc in agent.documents if doc.is_active and doc.status == "ready"]
        
        # Also include global documents
        global_result = await self.db.execute(
            select(Document)
            .where(Document.is_global == True)
            .where(Document.is_active == True)
            .where(Document.status == "ready")
        )
        global_docs = global_result.scalars().all()
        
        # Combine and deduplicate
        doc_ids = {doc.id for doc in documents}
        for doc in global_docs:
            if doc.id not in doc_ids:
                documents.append(doc)
        
        return documents
    
    async def retrieve_context(
        self,
        query: str,
        agent_id: str,
        limit: int = 5,
        min_score: float = 0.5
    ) -> str:
        """
        Retrieve relevant context from agent's documents.
        
        Returns formatted context string for LLM.
        """
        try:
            # Get agent's documents
            documents = await self.get_agent_documents(agent_id)
            
            if not documents:
                return ""
            
            # Get document IDs for filtering
            document_ids = [str(doc.id) for doc in documents]
            
            # Search for relevant chunks
            results = await self.processor.search(
                query=query,
                limit=limit,
                document_ids=document_ids
            )
            
            if not results:
                return ""
            
            # Filter by score
            relevant = [r for r in results if r.get("score", 0) >= min_score]
            
            if not relevant:
                return ""
            
            # Format context
            context_parts = []
            for i, result in enumerate(relevant, 1):
                context_parts.append(
                    f"[Documento: {result['document_name']}]\n"
                    f"{result['content']}"
                )
            
            context = "\n\n---\n\n".join(context_parts)
            
            logger.info(f"Retrieved {len(relevant)} relevant chunks for agent {agent_id}")
            
            return context
            
        except Exception as e:
            logger.error(f"RAG retrieval error: {e}")
            return ""
    
    async def format_rag_prompt(
        self,
        message: str,
        context: str,
        system_prompt: str = ""
    ) -> str:
        """
        Format a RAG-enhanced system prompt.
        """
        if not context:
            return system_prompt
        
        rag_addition = f"""

## Contexto da Base de Conhecimento

Use as seguintes informações da base de conhecimento para responder à pergunta do usuário. 
Se a informação não estiver no contexto, responda com base no seu conhecimento geral, 
mas informe que não encontrou essa informação específica nos documentos.

{context}

---

Lembre-se de citar a fonte (nome do documento) quando usar informações do contexto acima.
"""
        
        return system_prompt + rag_addition
    
    async def search_documents(
        self,
        query: str,
        document_ids: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Direct document search (for API endpoint).
        """
        return await self.processor.search(
            query=query,
            limit=limit,
            document_ids=document_ids
        )


async def get_rag_context(
    db: AsyncSession,
    agent_id: str,
    message: str,
    limit: int = 5
) -> str:
    """
    Convenience function to get RAG context for an agent.
    """
    service = RAGService(db)
    return await service.retrieve_context(
        query=message,
        agent_id=agent_id,
        limit=limit
    )
