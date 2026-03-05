import asyncio
import logging
from typing import List, Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.config import settings
from app.weaviate_client import get_weaviate

logger = logging.getLogger(__name__)

async def extract_and_save_memories(
    agent_id: str,
    contact_id: str,
    history: List[Dict[str, Any]],
    current_message: str
):
    """
    Asynchronously analyze the conversation history and current message 
    to extract new qualitative memories, and then save them to Weaviate.
    """
    if not history and not current_message:
        return

    # Check if we have enough new dialogue to warrant an extraction
    # A simple heuristical check could be used here (e.g. every 3 messages)
    # For now, we extract incrementally or dynamically based on the recent messages
    
    # We want to use a fast, structured LLM to extract qualitative facts
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.0,  # low temperature for factual extraction
        api_key=settings.OPENAI_API_KEY
    )
    
    system_prompt = """
Você é um sistema de extração de memória de contexto inteligente.
Sua tarefa é analisar o pequeno trecho final do diálogo entre um assistente (agente) e um usuário (contato).
Você deve identificar fatos qualitativos, temporais ou demográficos INÉDITOS sobre o usuário que não foram mencionados anteriormente e que sejam relevantes para interações futuras.

Exemplos de fatos relevantes para salvar:
- "Mora com 4 pessoas na casa"
- "Tem interesse no cristianismo e vontade de se batizar"
- "Trabalha no período da noite"
- "Está com problemas financeiros recentes"

Se não houver NENHUM fato novo relevante, responda EXATAMENTE com a palavra: NENHUM
Se houver fatos novos, liste-os como frases curtas e objetivas, uma por linha, sem marcadores e sem introduções.
"""

    # Build recent conversation context (e.g. last 3 turns)
    recent_history = history[-4:] if len(history) > 4 else history
    dialogue_str = ""
    for msg in recent_history:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        dialogue_str += f"{role.upper()}: {content}\n"
    
    dialogue_str += f"USER: {current_message}\n"
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Diálogo recente:\n{dialogue_str}")
    ]
    
    try:
        response = await llm.ainvoke(messages)
        extracted = response.content.strip()
        
        if extracted.upper() == "NENHUM" or not extracted:
            logger.info(f"[VectorMemory] No new memories extracted for contact {contact_id}")
            return
            
        # Split by lines if there are multiple facts
        facts = [f.strip("- ") for f in extracted.split("\n") if f.strip() and f.strip().upper() != "NENHUM"]
        
        if facts:
            weaviate_client = get_weaviate()
            for fact in facts:
                # Save each fact to Weaviate
                success = await weaviate_client.save_contact_memory(
                    agent_id=agent_id,
                    contact_id=contact_id,
                    content=fact
                )
                if success:
                    logger.info(f"[VectorMemory] Saved memory for {contact_id}: {fact[:50]}...")
                
    except Exception as e:
        logger.error(f"[VectorMemory] Error extracting memories: {e}")

