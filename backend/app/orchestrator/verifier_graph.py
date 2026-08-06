"""
Verifier Module — Lightweight response quality checker.
Performs deterministic tool-error detection + single-shot GPT-4o-mini semantic check.
Always uses gpt-4o-mini for speed and reliability — independent of the agent's model.
MAX_VERIFICATION_ATTEMPTS = 3.
"""
import json
import re
import logging
from typing import List, Optional, Dict, Any

from langchain_core.messages import ToolMessage, SystemMessage

logger = logging.getLogger(__name__)

MAX_VERIFICATION_ATTEMPTS = 3

# ── Deterministic tool-error patterns ────────────────────────────────────────
_ERROR_KEYWORDS = frozenset([
    "error", "erro:", "exception", "failed",
    "statuscode': 4", "statuscode': 5",
    "tool call blocked", "timeout",
    "unauthorized", "bad request", "not found",
])


def _check_tool_errors(messages: List[Any]) -> Optional[str]:
    """
    Scans ToolMessages for deterministic error signatures.
    Returns a description string if errors found, None otherwise.
    Zero LLM cost — pure string matching.
    """
    errors: List[str] = []

    for msg in messages:
        is_tool = isinstance(msg, ToolMessage) or (isinstance(msg, dict) and msg.get("role") == "tool")
        if not is_tool:
            continue

        content = msg.content if isinstance(msg, ToolMessage) else msg.get("content", "")
        tool_name = getattr(msg, "name", None) or (msg.get("name") if isinstance(msg, dict) else "tool")
        text = str(content).lower()

        # Keyword check
        if any(kw in text for kw in _ERROR_KEYWORDS):
            errors.append(f"'{tool_name}': {str(content)[:200]}")
            continue

        # JSON payload check
        stripped = str(content).strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                data = json.loads(stripped)
                if isinstance(data, dict) and (
                    data.get("error") or data.get("err")
                    or data.get("status") == "error"
                    or data.get("success") is False
                ):
                    errors.append(f"'{tool_name}': {stripped[:200]}")
            except (json.JSONDecodeError, ValueError):
                pass

    if errors:
        return "\n".join(errors)
    return None


def _get_verifier_llm():
    """
    Returns a dedicated gpt-4o-mini instance for verification.
    Fast, cheap, reliable — never depends on the agent's model.
    """
    from app.utils.llm_fallback import FallbackChatOpenAI as ChatOpenAI
    from app.config import settings

    return ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
        max_tokens=150,
        api_key=settings.OPENAI_API_KEY,
    )


async def _semantic_check(original_message: str, response: str) -> Optional[str]:
    """
    Single ultra-short GPT-4o-mini call (~100 prompt tokens).
    Returns None if approved, or a correction string if retry needed.
    """
    llm = _get_verifier_llm()

    prompt = (
        "Verifique se a RESPOSTA atende à PERGUNTA. "
        "Se sim, responda apenas: APPROVE\n"
        "Se não, responda: RETRY: <motivo curto>\n\n"
        f"PERGUNTA: {original_message[:500]}\n"
        f"RESPOSTA: {response[:1000]}"
    )

    try:
        result = await llm.ainvoke([SystemMessage(content=prompt)])
        text = (result.content if hasattr(result, "content") else str(result)).strip()

        if text.upper().startswith("APPROVE"):
            return None
        if text.upper().startswith("RETRY"):
            reason = text.split(":", 1)[1].strip() if ":" in text else text
            return reason or "Resposta incompleta"
    except Exception as e:
        logger.warning(f"[Verifier] ⚠️ Semantic check failed ({e}), approving by resilience.")

    return None


# ── Public API ───────────────────────────────────────────────────────────────

async def run_verifier(
    original_message: str,
    response: str,
    messages: List[Any],
    agent_config: Dict[str, Any],
    llm: Any = None,
    verification_attempt: int = 0,
) -> Dict[str, Any]:
    """
    Lightweight verifier — called after each agent execution turn.
    Always uses gpt-4o-mini internally (llm param kept for backward compat but ignored).

    Returns dict with:
      status: "SUCCESS" | "NEED_CORRECTION" | "MAX_ATTEMPTS_REACHED"
      correction_instruction: str | None
    """
    if verification_attempt >= MAX_VERIFICATION_ATTEMPTS:
        logger.warning("[Verifier] ⚠️ Max attempts reached, releasing response.")
        return {"status": "MAX_ATTEMPTS_REACHED", "correction_instruction": None}

    # ── Step 1: Deterministic tool-error scan (instant, zero cost) ──
    tool_err = _check_tool_errors(messages)
    if tool_err:
        logger.info(f"[Verifier] 🚨 Tool errors detected:\n{tool_err}")
        return {
            "status": "NEED_CORRECTION",
            "correction_instruction": (
                f"AUDITORIA (tentativa {verification_attempt + 1}/{MAX_VERIFICATION_ATTEMPTS}): "
                f"Ferramentas retornaram erros:\n{tool_err}\n"
                f"Corrija os parâmetros ou tente abordagem alternativa."
            ),
        }

    # ── Step 2: Quick semantic check via gpt-4o-mini ──
    retry_reason = await _semantic_check(original_message, response)
    if retry_reason:
        logger.info(f"[Verifier] 🔍 Semantic check: RETRY — {retry_reason}")
        return {
            "status": "NEED_CORRECTION",
            "correction_instruction": (
                f"AUDITORIA (tentativa {verification_attempt + 1}/{MAX_VERIFICATION_ATTEMPTS}): "
                f"{retry_reason}"
            ),
        }

    logger.info("[Verifier] ✅ Response approved.")
    return {"status": "SUCCESS", "correction_instruction": None}
