"""
VFS RAG 3.0 Service - Subagent-based knowledge retrieval from .md files
Uses a dedicated LLM subagent with file-reading tools to retrieve relevant context
"""
import os
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from uuid import UUID
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings

logger = logging.getLogger(__name__)

# VFS root directory
VFS_ROOT = Path("/app/vfs")
VFS_ROOT.mkdir(parents=True, exist_ok=True)


def get_vfs_root() -> Path:
    """Return the VFS root directory, ensuring it exists."""
    VFS_ROOT.mkdir(parents=True, exist_ok=True)
    return VFS_ROOT


async def get_vfs_context(
    db: AsyncSession,
    agent_id: str,
    message: str,
    max_files: int = 5,
) -> str:
    """
    RAG 3.0: Use a subagent to search and retrieve context from VFS .md files.
    
    Flow:
    1. Get agent's VFS knowledge bases
    2. Build an index of available files (title + summary)
    3. Use LLM subagent with tools to find and read relevant files
    4. Return synthesized context
    """
    try:
        from app.models.agent import Agent
        from app.models.vfs_knowledge_base import VFSKnowledgeBase, VFSFile

        # Get agent with VFS knowledge bases
        result = await db.execute(
            select(Agent)
            .options(
                selectinload(Agent.vfs_knowledge_bases)
                .selectinload(VFSKnowledgeBase.files)
            )
            .where(Agent.id == agent_id)
        )
        agent = result.scalar_one_or_none()
        if not agent or not agent.vfs_knowledge_bases:
            return ""

        # Collect all active files from active knowledge bases
        all_files = []
        for kb in agent.vfs_knowledge_bases:
            if not kb.is_active:
                continue
            for f in kb.files:
                all_files.append({
                    "id": str(f.id),
                    "knowledge_base": kb.name,
                    "filename": f.filename,
                    "title": f.title or f.filename,
                    "summary": f.summary or "",
                    "file_path": f.file_path,
                })

        if not all_files:
            return ""

        print(f"[VFS RAG 3.0] 📂 Found {len(all_files)} files across {len(agent.vfs_knowledge_bases)} knowledge bases")

        # Build the file index for the subagent
        file_index = "\n".join([
            f"- [{f['id']}] {f['title']} ({f['knowledge_base']}/{f['filename']}): {f['summary'][:200]}"
            for f in all_files
        ])

        # Use the subagent approach
        context = await _run_vfs_subagent(message, file_index, all_files, max_files)
        
        if context:
            print(f"[VFS RAG 3.0] ✅ Subagent returned context ({len(context)} chars)")
        
        return context

    except Exception as e:
        logger.error(f"[VFS RAG 3.0] Error: {e}")
        import traceback
        traceback.print_exc()
        return ""


async def _run_vfs_subagent(
    user_query: str,
    file_index: str,
    all_files: List[Dict[str, Any]],
    max_files: int = 5,
) -> str:
    """
    Run a LLM subagent that decides which files to read and synthesizes context.
    
    The subagent receives:
    - The user's query
    - An index of all available files (id, title, summary)
    - Tools to read file contents
    
    It returns a synthesized context string.
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage
    from langchain_core.tools import tool
    from langchain_core.runnables import RunnableConfig
    from langgraph.prebuilt import create_react_agent

    # Create file lookup
    file_lookup = {f["id"]: f for f in all_files}

    @tool
    def read_vfs_file(file_id: str) -> str:
        """Read the full content of a VFS .md file by its ID."""
        file_info = file_lookup.get(file_id)
        if not file_info:
            return f"Error: File with ID '{file_id}' not found."
        
        try:
            file_path = file_info["file_path"]
            if not os.path.exists(file_path):
                return f"Error: File not found at path {file_path}"
            
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Truncate very large files
            if len(content) > 8000:
                content = content[:8000] + "\n\n... [FILE TRUNCATED - showing first 8000 chars]"
            
            return f"# {file_info['title']}\n\n{content}"
        except Exception as e:
            return f"Error reading file: {str(e)}"

    @tool
    def search_vfs_files(query: str) -> str:
        """Search across all VFS file titles and summaries for relevant matches. Returns matching file IDs."""
        query_lower = query.lower()
        matches = []
        for f in all_files:
            title = (f.get("title") or "").lower()
            summary = (f.get("summary") or "").lower()
            filename = (f.get("filename") or "").lower()
            if query_lower in title or query_lower in summary or query_lower in filename:
                matches.append(f"[{f['id']}] {f['title']} - {f['summary'][:100]}")
        
        if not matches:
            return "No files matched the search query. Try different keywords or read the file index."
        return "\n".join(matches[:10])

    # Create LLM for the subagent
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
        api_key=settings.OPENAI_API_KEY,
    )

    system_prompt = f"""Você é um subagente de RAG 3.0. Sua única função é encontrar e ler arquivos .md relevantes para responder à consulta do usuário.

## Arquivos Disponíveis (Índice)

{file_index}

## Suas Ferramentas

1. `search_vfs_files(query)` - Busca por palavras-chave nos títulos e resumos dos arquivos
2. `read_vfs_file(file_id)` - Lê o conteúdo completo de um arquivo por ID

## Regras

1. Analise a consulta do usuário e identifique quais arquivos do índice são relevantes
2. Use `search_vfs_files` se precisar buscar por palavras-chave
3. Use `read_vfs_file` para ler os arquivos que parecem relevantes (máximo {max_files} arquivos)
4. Sintetize as informações encontradas em um contexto claro e organizado
5. Se nenhum arquivo for relevante, responda apenas "SEM CONTEXTO RELEVANTE"
6. NÃO invente informações - use apenas o que encontrar nos arquivos
7. Cite o nome/título do arquivo quando usar suas informações"""

    run_config = RunnableConfig(
        run_name="VFS RAG 3.0 Subagent",
        metadata={"subagent": True, "type": "vfs_rag"},
        tags=["vfs-rag", "subagent"]
    )

    try:
        react_agent = create_react_agent(
            model=llm,
            tools=[read_vfs_file, search_vfs_files]
        )

        result = await react_agent.ainvoke(
            {"messages": [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Encontre informações relevantes para esta consulta: {user_query}")
            ]},
            config=run_config
        )

        # Extract the final response
        from langchain_core.messages import AIMessage
        final_messages = result.get("messages", [])
        for msg in reversed(final_messages):
            if isinstance(msg, AIMessage) and msg.content:
                if not (hasattr(msg, "tool_calls") and msg.tool_calls):
                    response = msg.content.strip()
                    if "SEM CONTEXTO RELEVANTE" in response:
                        return ""
                    return response

        return ""

    except Exception as e:
        logger.error(f"[VFS RAG 3.0] Subagent error: {e}")
        import traceback
        traceback.print_exc()
        return ""
