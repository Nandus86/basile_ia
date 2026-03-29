"""
Callbacks customizados para rastreamento de custo no LangSmith.

OpenRouterCostCallback:
  - Intercepta a resposta do LLM após cada invocação.
  - Estratégia B (custo real): consulta GET /api/v1/generation?id=... no OpenRouter.
  - Estratégia A (fallback): estima com base em tabela de preços local.
  - Injeta os metadados de custo no trace do LangSmith via update_run().

OpenAICostCallback:
  - Captura tokens de chamadas diretas à OpenAI e injeta no mesmo formato.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

import httpx
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tabela de preços local (fallback — Estratégia A)
# Preços em USD por 1.000 tokens (prompt / completion)
# Atualizado: 2025-03. Mantenha sincronizado com https://openrouter.ai/models
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
        # Tenta match parcial (ex: "google/gemini-flash-1.5-8b-exp" → "google/gemini-flash-1.5-8b")
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
    Callback assíncrono que captura o custo real de cada chamada LLM ao
    OpenRouter e injeta os metadados no trace do LangSmith.

    Fluxo:
      1. on_llm_end → extrai tokens e generation_id da resposta.
      2. Chama GET /api/v1/generation?id=... no OpenRouter (Estratégia B).
      3. Se falhar, estima via tabela local (Estratégia A).
      4. Atualiza o trace do LangSmith via langsmith_client.update_run().

    Args:
        openrouter_api_key: Chave da API do OpenRouter.
        model: ID do modelo usado (ex: "google/gemini-flash-1.5").
        is_openrouter: Se True, usa /api/v1/generation para custo real.
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
        **kwargs: Any,
    ) -> None:
        """Intercepta o fim de cada chamada LLM e injeta o custo no LangSmith."""
        try:
            # --- 1. Extrair tokens ---
            prompt_tokens = 0
            completion_tokens = 0
            generation_id: Optional[str] = None

            if response.llm_output:
                usage = response.llm_output.get("token_usage") or response.llm_output.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)

            # Fallback: usage_metadata por geração individual
            if not prompt_tokens and response.generations:
                for gen_list in response.generations:
                    for gen in gen_list:
                        meta = getattr(gen, "generation_info", None) or {}
                        usage = meta.get("usage", {}) or {}
                        prompt_tokens += usage.get("prompt_tokens", 0)
                        completion_tokens += usage.get("completion_tokens", 0)
                        # generation_id vem no response_metadata em alguns adapters
                        if not generation_id:
                            generation_id = meta.get("id") or meta.get("x-generation-id")

            total_tokens = prompt_tokens + completion_tokens

            # --- 2. Buscar custo real (Estratégia B) ---
            cost_usd: Optional[float] = None
            cost_source = "unknown"

            if self.is_openrouter and generation_id:
                cost_usd = await self._fetch_real_cost(generation_id)
                if cost_usd is not None:
                    cost_source = "openrouter_api"
                    logger.info(
                        f"[CostCallback] 💰 Custo real OpenRouter: ${cost_usd:.6f} USD "
                        f"(model={self.model}, id={generation_id})"
                    )

            # --- 3. Fallback — estimativa (Estratégia A) ---
            if cost_usd is None and total_tokens > 0:
                cost_usd = _estimate_cost(self.model, prompt_tokens, completion_tokens)
                if cost_usd is not None:
                    cost_source = "local_estimate"
                    logger.info(
                        f"[CostCallback] 💡 Custo estimado: ${cost_usd:.6f} USD "
                        f"(model={self.model}, tokens={total_tokens})"
                    )
                else:
                    logger.warning(
                        f"[CostCallback] ⚠️ Modelo '{self.model}' não encontrado na "
                        f"tabela local. Adicione o preço em callbacks.py."
                    )

            # --- 4. Injetar metadados no trace do LangSmith ---
            extra_metadata: Dict[str, Any] = {
                "model": self.model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cost_source": cost_source,
                "provider": "openrouter" if self.is_openrouter else "openai",
            }
            if cost_usd is not None:
                extra_metadata["cost_usd"] = cost_usd

            cost_str = f"${cost_usd:.6f}" if cost_usd is not None else "$N/A"

            try:
                from langsmith import Client as LangSmithClient
                ls_client = LangSmithClient()
                ls_client.update_run(
                    run_id=str(run_id),
                    extra={"metadata": extra_metadata},
                )
                logger.info(
                    f"[CostCallback] ✅ LangSmith run {run_id} atualizado com custo "
                    f"{cost_str} ({cost_source})"
                )
            except Exception as ls_exc:
                exc_str = str(ls_exc)
                if "409" in exc_str or "Conflict" in exc_str:
                    # Run já foi finalizado pelo LangSmith — esperado em ReAct agents
                    logger.debug(
                        f"[CostCallback] ℹ️ LangSmith run {run_id} já finalizado (409). "
                        f"Custo capturado localmente: {cost_str}"
                    )
                else:
                    logger.warning(f"[CostCallback] ⚠️ Falha ao atualizar LangSmith run: {ls_exc}")

        except Exception as exc:
            # Nunca deixar o callback quebrar o fluxo principal
            logger.error(f"[CostCallback] ❌ Erro inesperado no callback de custo: {exc}", exc_info=True)


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
