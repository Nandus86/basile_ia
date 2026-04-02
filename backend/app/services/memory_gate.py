"""
Memory Gate — pré-filtro heurístico barato para vector memory extraction.

Decide se vale a pena chamar o LLM de extração de memórias, evitando
custo desnecessário em interações triviais (saudações, agradecimentos, etc).
"""
import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# ── Padrões triviais (lowercase) que nunca geram memória útil ──

_TRIVIAL_PATTERNS = [
    # Saudações
    r"^(oi+|ol[áa]+|e? ?a[íi]+|opa+|hey+|hi+|hello)$",
    r"^(bom dia|boa tarde|boa noite|bom dia!|boa tarde!|boa noite!)$",
    r"^(tudo bem|tudo certo|como vai|e a[ií]|blz)$",
    # Agradecimentos
    r"^(obrigad[oa]|valeu+|brigad[oa]|thanks+|vlw+|tmj)$",
    r"^(muito obrigad[oa]|obrigado!|valeu!|brigada!)$",
    # Confirmações curtas
    r"^(ok+|t[aá]+|certo|beleza|entendi|show|perfeito|sim|n[aã]o|pode ser|isso|exato)$",
    r"^(ok!|tá!|certo!|beleza!|entendi!|show!|perfeito!|sim!|não!)$",
    # Despedidas
    r"^(tchau+|at[eé] (mais|logo|depois)|flw+|falou|at[eé]|bye+)$",
    r"^(tchau!|até mais!|até logo!|flw!|falou!)$",
    # Reações curtas
    r"^(legal|bacana|massa|top|incrível|que bom|parab[eé]ns)$",
    r"^(haha+|kkk+|rsrs+|😂|👍|🙏|❤️|😊)$",
    r"^(sim+|nao+|não+|si+|yes+|no+)$",
]

_TRIVIAL_RE = [re.compile(p, re.IGNORECASE) for p in _TRIVIAL_PATTERNS]

# ── Palavras-chave de alta prioridade (sempre extrair) ──

_CORRECTION_KEYWORDS = [
    "não sou", "nao sou", "na verdade", "errado", "está errado",
    "tá errado", "ta errado", "não é isso", "nao e isso",
    "me chama de", "quero que me chame", "não me chame", "nao me chame",
    "corrigindo", "correção", "corrigir",
]

_PREFERENCE_KEYWORDS = [
    "prefiro", "gostaria que", "não gosto", "nao gosto",
    "me incomoda", "pode ser mais", "quero que você",
    "não quero", "nao quero", "evite", "pare de",
    "meu nome é", "meu nome e", "me chamo",
]

_HIGH_PRIORITY_KEYWORDS = _CORRECTION_KEYWORDS + _PREFERENCE_KEYWORDS


def _is_trivial_message(message: str) -> bool:
    """Check if a message is trivial (saudação, agradecimento, etc)."""
    cleaned = message.strip()
    if not cleaned:
        return True

    # Remove pontuação final para comparação
    cleaned_no_punct = cleaned.rstrip("!.?,")

    for pattern in _TRIVIAL_RE:
        if pattern.match(cleaned_no_punct):
            return True

    # Menos de 3 palavras no geral
    words = cleaned_no_punct.split()
    if len(words) <= 2:
        return True

    return False


def _has_high_priority_keywords(message: str) -> bool:
    """Check if message contains correction or preference keywords."""
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in _HIGH_PRIORITY_KEYWORDS)


def _is_response_trivial(response: str) -> bool:
    """Check if agent response is too short to generate useful memories."""
    if not response:
        return True
    if len(response) < 50:
        return True
    return False


def _is_repetitive_with_history(message: str, history: List[Dict[str, Any]]) -> bool:
    """Check if user message is very similar to recent user messages in history."""
    if not history:
        return False

    msg_lower = message.lower().strip()
    msg_words = set(re.findall(r'\w+', msg_lower))
    if not msg_words:
        return True

    # Check last 3 user messages
    recent_user_msgs = [
        m.get("content", "").lower().strip()
        for m in history[-6:]
        if m.get("role") == "user"
    ]

    for prev_msg in recent_user_msgs[-3:]:
        if not prev_msg:
            continue
        prev_words = set(re.findall(r'\w+', prev_msg))
        if not prev_words:
            continue
        overlap = len(msg_words & prev_words) / max(len(msg_words | prev_words), 1)
        if overlap > 0.8:
            return True

    return False


def should_extract_memories(
    user_message: str,
    agent_response: str = "",
    history: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """
    Decide se vale a pena extrair memórias desta interação.

    Returns:
        True se deve extrair (interação substantiva ou alta prioridade).
        False se é interação trivial que não gerará memória útil.

    Lógica:
    1. Palavras-chave de alta prioridade (correção/preferência) → SEMPRE extrair
    2. Mensagem trivial + resposta trivial → NÃO extrair
    3. Mensagem muito curta (< 15 chars) sem keywords → NÃO extrair
    4. Mensagem repetitiva com histórico recente → NÃO extrair
    5. Caso contrário → extrair
    """
    if not user_message or not user_message.strip():
        return False

    msg = user_message.strip()

    # 1. Alta prioridade: correções e preferências SEMPRE passam
    if _has_high_priority_keywords(msg):
        logger.info(f"[MemoryGate] ✅ High-priority keywords detected, extracting")
        return True

    # 2. Mensagem trivial E resposta trivial → skip
    if _is_trivial_message(msg) and _is_response_trivial(agent_response):
        logger.info(f"[MemoryGate] ⏭️ Trivial interaction, skipping extraction")
        return False

    # 3. Mensagem muito curta sem keywords
    if len(msg) < 15 and not _has_high_priority_keywords(msg):
        logger.info(f"[MemoryGate] ⏭️ Message too short ({len(msg)} chars), skipping")
        return False

    # 4. Repetitiva com histórico
    if _is_repetitive_with_history(msg, history or []):
        logger.info(f"[MemoryGate] ⏭️ Repetitive with recent history, skipping")
        return False

    # 5. Passou nos filtros → extrair
    return True
