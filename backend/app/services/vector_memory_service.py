"""
Vector Memory Service — Intelligent Learning System

Extracts and saves different types of memories:
1. FACTS: General qualitative facts about the user (contact-level)
2. CORRECTIONS: When the user corrects the agent's assumptions (contact-level, high priority)
3. PREFERENCES: User-stated preferences (contact-level)
4. SELF_CORRECTIONS: Agent-level learning when it violates its own prompt rules (agent-level)
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.config import settings
from app.weaviate_client import get_weaviate

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# 1. Contact-level memory extraction (facts + corrections + preferences)
# ─────────────────────────────────────────────────────────────

async def extract_and_save_memories(
    agent_id: str,
    contact_id: str,
    history: List[Dict[str, Any]],
    current_message: str
):
    """
    Asynchronously analyze the conversation history and current message 
    to extract new qualitative memories, corrections, and preferences.
    Saves them to Weaviate with appropriate memory_type tags.
    """
    if not history and not current_message:
        return

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.0,
        api_key=settings.OPENAI_API_KEY
    )
    
    # Build recent conversation context
    recent_history = history[-4:] if len(history) > 4 else history
    dialogue_str = ""
    for msg in recent_history:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        dialogue_str += f"{role.upper()}: {content}\n"
    dialogue_str += f"USER: {current_message}\n"

    # Run all three extraction tasks in parallel
    await asyncio.gather(
        _extract_corrections(llm, agent_id, contact_id, dialogue_str),
        _extract_preferences(llm, agent_id, contact_id, dialogue_str),
        _extract_facts(llm, agent_id, contact_id, dialogue_str),
        return_exceptions=True
    )


async def _extract_corrections(llm, agent_id: str, contact_id: str, dialogue: str):
    """Detect if the user is correcting an assumption made by the assistant."""
    system_prompt = """Analise a última interação abaixo entre assistente e usuário.
Identifique se o USUÁRIO está CORRIGINDO uma suposição ou afirmação feita pelo ASSISTENTE.

Exemplos de correção:
- Assistente: "Paz do Senhor, pastor Fernando" → Usuário: "Não sou pastor"
  → CORREÇÃO: "O usuário NÃO é pastor. Nunca tratá-lo como pastor."
- Assistente: "Como está sua esposa?" → Usuário: "Eu sou solteiro" 
  → CORREÇÃO: "O usuário é solteiro. Não perguntar sobre esposa/cônjuge."
- Assistente: "Boa tarde!" → Usuário: "Na verdade aqui já é noite"
  → CORREÇÃO: "O usuário está em fuso horário diferente. Verificar horário antes de cumprimentar."

Se NÃO houver correção, responda EXATAMENTE: NENHUM
Se houver correção, escreva UMA frase imperativa clara começando com "Lembrar: ..."
Apenas UMA correção por vez, a mais importante."""

    try:
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Diálogo recente:\n{dialogue}")
        ])
        extracted = response.content.strip()
        
        if extracted.upper() == "NENHUM" or not extracted:
            return
        
        weaviate_client = get_weaviate()
        await weaviate_client.save_contact_memory(
            agent_id=agent_id,
            contact_id=contact_id,
            content=f"⚠️ CORREÇÃO: {extracted}",
            metadata={"priority": "high"},
            memory_type="correction"
        )
        logger.info(f"[VectorMemory] 🔴 Correction saved for {contact_id}: {extracted[:60]}...")
        
    except Exception as e:
        logger.error(f"[VectorMemory] Error extracting corrections: {e}")


async def _extract_preferences(llm, agent_id: str, contact_id: str, dialogue: str):
    """Detect if the user is stating a preference."""
    system_prompt = """Analise a última interação abaixo entre assistente e usuário.
Identifique se o USUÁRIO está expressando uma PREFERÊNCIA pessoal que deve ser lembrada.

Exemplos de preferência:
- "Prefiro que me chame de Fernandinho" → PREFERÊNCIA: "Prefere ser chamado de Fernandinho"
- "Não gosto de receber mensagens de manhã" → PREFERÊNCIA: "Não gosta de receber mensagens de manhã"
- "Pode me falar de forma mais informal" → PREFERÊNCIA: "Prefere comunicação informal"

Se NÃO houver preferência, responda EXATAMENTE: NENHUM
Se houver preferência, escreva UMA frase curta descrevendo a preferência.
Apenas UMA preferência por vez, a mais relevante."""

    try:
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Diálogo recente:\n{dialogue}")
        ])
        extracted = response.content.strip()
        
        if extracted.upper() == "NENHUM" or not extracted:
            return
        
        weaviate_client = get_weaviate()
        await weaviate_client.save_contact_memory(
            agent_id=agent_id,
            contact_id=contact_id,
            content=f"💡 PREFERÊNCIA: {extracted}",
            metadata={"priority": "medium"},
            memory_type="preference"
        )
        logger.info(f"[VectorMemory] 🟡 Preference saved for {contact_id}: {extracted[:60]}...")
        
    except Exception as e:
        logger.error(f"[VectorMemory] Error extracting preferences: {e}")


async def _extract_facts(llm, agent_id: str, contact_id: str, dialogue: str):
    """Extract general qualitative facts about the user."""
    system_prompt = """Você é um sistema de extração de memória de contexto inteligente.
Sua tarefa é analisar o pequeno trecho final do diálogo entre um assistente (agente) e um usuário (contato).
Você deve identificar fatos qualitativos, temporais ou demográficos INÉDITOS sobre o usuário que não foram mencionados anteriormente e que sejam relevantes para interações futuras.

Exemplos de fatos relevantes para salvar:
- "Mora com 4 pessoas na casa"
- "Tem interesse no cristianismo e vontade de se batizar"
- "Trabalha no período da noite"
- "Está com problemas financeiros recentes"

NÃO inclua correções ou preferências (esses são tratados separadamente).
Se não houver NENHUM fato novo relevante, responda EXATAMENTE com a palavra: NENHUM
Se houver fatos novos, liste-os como frases curtas e objetivas, uma por linha, sem marcadores e sem introduções."""

    try:
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Diálogo recente:\n{dialogue}")
        ])
        extracted = response.content.strip()
        
        if extracted.upper() == "NENHUM" or not extracted:
            logger.info(f"[VectorMemory] No new facts extracted for contact {contact_id}")
            return
            
        facts = [f.strip("- ") for f in extracted.split("\n") if f.strip() and f.strip().upper() != "NENHUM"]
        
        if facts:
            weaviate_client = get_weaviate()
            for fact in facts:
                success = await weaviate_client.save_contact_memory(
                    agent_id=agent_id,
                    contact_id=contact_id,
                    content=fact,
                    memory_type="fact"
                )
                if success:
                    logger.info(f"[VectorMemory] 🟢 Fact saved for {contact_id}: {fact[:50]}...")
                
    except Exception as e:
        logger.error(f"[VectorMemory] Error extracting facts: {e}")


# ─────────────────────────────────────────────────────────────
# 2. Agent-level self-correction extraction
# ─────────────────────────────────────────────────────────────

async def extract_agent_self_corrections(
    agent_id: str,
    system_prompt: str,
    agent_response: str,
    user_message: str,
    history: Optional[List[Dict[str, Any]]] = None,
):
    """
    Analyze if the agent's response violates any rule in its own system_prompt.
    If so, save a self-correction memory at the agent level.
    
    This runs asynchronously after each response to enable continuous learning.
    """
    if not system_prompt or not agent_response:
        return

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.0,
        api_key=settings.OPENAI_API_KEY
    )

    # Build context of rules the agent should follow
    check_prompt = """Você é um sistema de auditoria de IA que verifica se um agente violou suas próprias regras.

Abaixo está o PROMPT DO SISTEMA (as regras que o agente deveria seguir) e a RESPOSTA que ele deu.

Sua tarefa:
1. Analise se a RESPOSTA viola alguma regra ou instrução definida no PROMPT DO SISTEMA
2. Se houve violação, descreva-a de forma IMPERATIVA para que o agente aprenda

Exemplos de violação:
- Prompt diz "não usar saudação após a primeira interação" mas o agente cumprimentou na 3ª mensagem
  → "NÃO cumprimentar após a primeira interação. O agente usou saudação indevidamente."
- Prompt diz "sempre perguntar o nome do usuário" mas o agente não perguntou
  → "SEMPRE perguntar o nome do usuário na primeira interação."

Se NÃO houve violação, responda EXATAMENTE: NENHUM
Se houve violação, escreva UMA frase imperativa sobre a regra violada.
Apenas a violação MAIS IMPORTANTE."""

    # Include some history for context
    history_str = ""
    if history:
        recent = history[-3:]
        for msg in recent:
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "")[:200]
            history_str += f"{role}: {content}\n"

    analysis_input = f"""PROMPT DO SISTEMA (regras):
---
{system_prompt[:3000]}
---

HISTÓRICO RECENTE:
{history_str}

MENSAGEM DO USUÁRIO:
{user_message[:500]}

RESPOSTA DO AGENTE:
{agent_response[:1500]}"""

    try:
        response = await llm.ainvoke([
            SystemMessage(content=check_prompt),
            HumanMessage(content=analysis_input)
        ])
        extracted = response.content.strip()
        
        if extracted.upper() == "NENHUM" or not extracted:
            return
        
        weaviate_client = get_weaviate()
        await weaviate_client.save_agent_self_memory(
            agent_id=agent_id,
            content=f"🔧 AUTO-CORREÇÃO: {extracted}",
            memory_type="self_correction",
            metadata={"trigger_message": user_message[:200]}
        )
        logger.info(f"[VectorMemory] 🔧 Agent self-correction saved for agent {agent_id}: {extracted[:60]}...")
        
    except Exception as e:
        logger.error(f"[VectorMemory] Error extracting agent self-corrections: {e}")
