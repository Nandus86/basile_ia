"""
Callbacks customizados para rastreamento de custo no LangSmith.

OpenRouterCostCallback:
  - Intercepta on_llm_end de cada chamada LLM.
  - Extrai custo DIRETO da resposta do OpenRouter (token_usage.cost) — sem API
    call extra na maioria dos casos.
  - Fallback 1 (Estratégia B): GET /api/v1/generation?id=... no OpenRouter.
  - Fallback 2 (Estratégia A): tabela de preços local.
  - Injeta os dados no LangSmith run via update_run e/ou create_feedback.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tabela de preços local (fallback — Estratégia A)
# Preços em USD por 1.000 tokens (prompt / completion)
# Atualizado: 2026-03. Mantenha sincronizado com https://openrouter.ai/models
# ---------------------------------------------------------------------------
_PRICE_TABLE: Dict[str, Dict[str, float]] = {
    # Google
    "google/gemini-flash-1.5":          {"prompt": 0.000075, "completion": 0.0003},
    "google/gemini-flash-1.5-8b":       {"prompt": 0.0000375, "completion": 0.00015},
    "google/gemini-pro-1.5":            {"prompt": 0.00125,  "completion": 0.005},
    "google/gemini-2.0-flash-001":      {"prompt": 0.0001,   "completion": 0.0004},
    "google/gemini-2.5-pro-preview":    {"prompt": 0.00125,  "completion": 0.01},
    # Qwen (Alibaba)
    "qwen/qwen3.5-flash-02-23":         {"prompt": 0.000065, "completion": 0.00026},
    "qwen/qwen3-235b-a22b-2507":        {"prompt": 0.0003,   "completion": 0.0012},
    "qwen/qwen-2.5-72b-instruct":       {"prompt": 0.00023,  "completion": 0.00033},
    "qwen/qwen-2.5-coder-32b-instruct": {"prompt": 0.00018,  "completion": 0.00018},
    # OpenAI via OpenRouter
    "openai/gpt-4o":                    {"prompt": 0.0025,   "completion": 0.01},
    "openai/gpt-4o-mini":               {"prompt": 0.00015,  "completion": 0.0006},
    "openai/gpt-4-turbo":               {"prompt": 0.01,     "completion": 0.03},
    # Anthropic
    "anthropic/claude-3.5-sonnet":      {"prompt": 0.003,    "completion": 0.015},
    "anthropic/claude-3-haiku":         {"prompt": 0.00025,  "completion": 0.00125},
    # Meta
    "meta-llama/llama-3.1-8b-instruct":  {"prompt": 0.000055, "completion": 0.000055},
    "meta-llama/llama-3.1-70b-instruct": {"prompt": 0.00052,  "completion": 0.00075},
    # Mistral
    "mistralai/mistral-7b-instruct":    {"prompt": 0.000055,  "completion": 0.000055},
    "mistralai/mixtral-8x7b-instruct":  {"prompt": 0.00024,   "completion": 0.00024},
    # DeepSeek
    "deepseek/deepseek-chat-v3-0324":   {"prompt": 0.0003,   "completion": 0.0009},
    "deepseek/deepseek-r1":             {"prompt": 0.0005,   "completion": 0.002},
    # OpenAI direto (não via OpenRouter)
    "gpt-4o":                           {"prompt": 0.0025,   "completion": 0.01},
    "gpt-4o-mini":                      {"prompt": 0.00015,  "completion": 0.0006},
    "gpt-4-turbo":                      {"prompt": 0.01,     "completion": 0.03},
    "gpt-3.5-turbo":                    {"prompt": 0.0005,   "completion": 0.0015},
}


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> Optional[float]:
    """Estima o custo (USD) com base na tabela local de preços."""
    prices = _PRICE_TABLE.get(model)
    if not prices:
        # Match parcial (ex: "google/gemini-flash-1.5-8b-exp" → "google/gemini-flash-1.5-8b")
        for key, p in _PRICE_TABLE.items():
            if model.startswith(key) or key in model:
                prices = p
                break

    if not prices:
        return None

    cost = (prompt_tokens / 1000 * prices["prompt"]) + (completion_tokens / 1000 * prices["completion"])
    return round(cost, 8)


# ---------------------------------------------------------------------------
# Callback Principal
# ---------------------------------------------------------------------------

class OpenRouterCostCallback(AsyncCallbackHandler):
    """
    Callback assíncrono que captura o custo de cada chamada LLM e injeta
    os metadados no trace do LangSmith.

    Estratégias de custo (em ordem de prioridade):
      1. Custo direto do OpenRouter (llm_output.token_usage.cost) — SEM API call.
      2. GET /api/v1/generation?id=... no OpenRouter — com generation_id.
      3. Estimativa local via _PRICE_TABLE.

    Args:
        openrouter_api_key: Chave da API do OpenRouter.
        model: ID do modelo usado (ex: "google/gemini-flash-1.5").
        is_openrouter: Se True, tenta extrair custo do OpenRouter.
    """

    def __init__(
        self,
        openrouter_api_key: str,
        model: str,
        is_openrouter: bool = True,
    ):
        super().__init__()
        self.openrouter_api_key = openrouter_api_key
        self.model = model
        self.is_openrouter = is_openrouter

    async def _fetch_real_cost(self, generation_id: str) -> Optional[float]:
        """Consulta o custo real no endpoint de geração do OpenRouter."""
        url = f"https://openrouter.ai/api/v1/generation?id={generation_id}"
        headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    cost = data.get("data", {}).get("total_cost")
                    if cost is not None:
                        return float(cost)
        except Exception as exc:
            logger.debug(f"[CostCallback] Falha ao buscar custo real do OpenRouter: {exc}")
        return None

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Intercepta o fim de cada chamada LLM e injeta o custo no LangSmith."""
        try:
            # --- 1. Extrair tokens e custo do llm_output ---
            prompt_tokens = 0
            completion_tokens = 0
            cost_usd: Optional[float] = None
            cost_source = "unknown"
            generation_id: Optional[str] = None

            if response.llm_output:
                usage = response.llm_output.get("token_usage") or response.llm_output.get("usage") or {}
                prompt_tokens = usage.get("prompt_tokens", 0) or 0
                completion_tokens = usage.get("completion_tokens", 0) or 0

                # ** CHAVE **: OpenRouter retorna cost direto em token_usage!
                raw_cost = usage.get("cost")
                if raw_cost is not None:
                    cost_usd = float(raw_cost)
                    cost_source = "openrouter_response"

                # System fingerprint / id (pode conter o generation_id)
                generation_id = response.llm_output.get("system_fingerprint") or None

            # --- 2. Extrair generation_id a partir do message.response_metadata ---
            if response.generations:
                for gen_list in response.generations:
                    for gen in gen_list:
                        # Token fallback: generation_info
                        if not prompt_tokens:
                            gi = getattr(gen, "generation_info", None) or {}
                            gi_usage = gi.get("usage") or {}
                            prompt_tokens += gi_usage.get("prompt_tokens", 0) or 0
                            completion_tokens += gi_usage.get("completion_tokens", 0) or 0

                        # Extrair generation_id do message.response_metadata
                        msg = getattr(gen, "message", None)
                        if msg and not generation_id:
                            rm = getattr(msg, "response_metadata", None) or {}
                            generation_id = rm.get("id")  # ex: "gen-1774823550-..."

                            # Se o cost não veio no llm_output, tenta do response_metadata
                            if cost_usd is None:
                                rm_usage = rm.get("token_usage") or {}
                                rm_cost = rm_usage.get("cost")
                                if rm_cost is not None:
                                    cost_usd = float(rm_cost)
                                    cost_source = "openrouter_response_metadata"

                                # Também extrai tokens do usage_metadata da mensagem
                                if not prompt_tokens:
                                    um = getattr(msg, "usage_metadata", None) or {}
                                    prompt_tokens = um.get("input_tokens", 0) or 0
                                    completion_tokens = um.get("output_tokens", 0) or 0

            total_tokens = prompt_tokens + completion_tokens

            # --- 3. Fallback: buscar custo via API do OpenRouter (Estratégia B) ---
            if cost_usd is None and self.is_openrouter and generation_id:
                cost_usd = await self._fetch_real_cost(generation_id)
                if cost_usd is not None:
                    cost_source = "openrouter_api"

            # --- 4. Fallback: estimativa local (Estratégia A) ---
            if cost_usd is None and total_tokens > 0:
                cost_usd = _estimate_cost(self.model, prompt_tokens, completion_tokens)
                if cost_usd is not None:
                    cost_source = "local_estimate"
                else:
                    logger.warning(
                        f"[CostCallback] ⚠️ Modelo '{self.model}' sem preço no OpenRouter "
                        f"response e não encontrado na tabela local. Adicione em callbacks.py."
                    )

            cost_str = f"${cost_usd:.6f}" if cost_usd is not None else "$N/A"

            # --- 5. Log estruturado ---
            logger.info(
                f"[CostCallback] 💰 {cost_str} ({cost_source}) | "
                f"model={self.model} | tokens={total_tokens} "
                f"(in={prompt_tokens}, out={completion_tokens})"
            )

            # --- 6. Injetar no LangSmith ---
            cost_metadata: Dict[str, Any] = {
                "cost_usd": cost_usd,
                "cost_source": cost_source,
                "model": self.model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "provider": "openrouter" if self.is_openrouter else "openai",
            }
            if generation_id:
                cost_metadata["generation_id"] = generation_id

            self._inject_langsmith(run_id, parent_run_id, cost_metadata, cost_str, cost_source)

        except Exception as exc:
            # NUNCA deixar o callback quebrar o fluxo principal
            logger.error(f"[CostCallback] ❌ Erro inesperado: {exc}", exc_info=True)

    def _inject_langsmith(
        self,
        run_id: UUID,
        parent_run_id: Optional[UUID],
        cost_metadata: Dict[str, Any],
        cost_str: str,
        cost_source: str,
    ) -> None:
        """Tenta injetar os dados de custo no LangSmith de múltiplas formas."""
        try:
            from langsmith import Client as LangSmithClient
            ls = LangSmithClient()

            target_run = str(parent_run_id) if parent_run_id else str(run_id)

            # Abordagem 1: update_run com extra.metadata (visível na aba Metadata)
            try:
                ls.update_run(
                    run_id=target_run,
                    extra={"metadata": cost_metadata},
                )
                logger.info(
                    f"[CostCallback] ✅ LangSmith run {target_run} atualizado: {cost_str} ({cost_source})"
                )
                return  # Sucesso, não precisa de fallback
            except Exception as update_exc:
                exc_str = str(update_exc)
                if "409" in exc_str or "Conflict" in exc_str:
                    logger.debug(f"[CostCallback] ℹ️ Run {target_run} já finalizado (409), tentando feedback...")
                else:
                    logger.debug(f"[CostCallback] ⚠️ update_run falhou: {update_exc}, tentando feedback...")

            # Abordagem 2: create_feedback (funciona mesmo após run finalizado)
            cost_usd = cost_metadata.get("cost_usd")
            if cost_usd is not None:
                ls.create_feedback(
                    run_id=str(run_id),
                    key="openrouter_cost",
                    score=cost_usd,
                    comment=(
                        f"model={cost_metadata['model']} | "
                        f"tokens={cost_metadata['total_tokens']} | "
                        f"source={cost_source}"
                    ),
                )
                logger.info(
                    f"[CostCallback] ✅ LangSmith feedback criado para run {run_id}: {cost_str}"
                )

        except Exception as ls_exc:
            logger.warning(f"[CostCallback] ⚠️ Falha total ao injetar no LangSmith: {ls_exc}")


# ---------------------------------------------------------------------------
# Fábrica de callbacks — ponto de entrada do agent_factory
# ---------------------------------------------------------------------------

def build_cost_callbacks(
    model: str,
    openrouter_api_key: str,
    openai_api_key: Optional[str] = None,
) -> List[OpenRouterCostCallback]:
    """
    Retorna a lista de callbacks de custo adequada para o modelo.

    Args:
        model: ID do modelo (ex: "google/gemini-flash-1.5" ou "gpt-4o-mini").
        openrouter_api_key: Chave da API do OpenRouter.
        openai_api_key: Chave da OpenAI (não usada ainda, reservado para futuro).

    Returns:
        Lista com um callback configurado para o provider correto.
    """
    openrouter_specials = ["sambanova", "groq"]
    is_openrouter = "/" in model or model in openrouter_specials

    return [
        OpenRouterCostCallback(
            openrouter_api_key=openrouter_api_key,
            model=model,
            is_openrouter=is_openrouter,
        )
    ]
