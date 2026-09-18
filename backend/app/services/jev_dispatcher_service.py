"""
JevDispatcherService — Roteador Genérico de Ferramentas via TypeSafe JEV
========================================================================
Permite que qualquer agente especialista com a configuração {"jev": true}
em seu config JSON execute suas ferramentas com ultra-baixa latência (~200ms)
utilizando TypeSafe JEV (~typesafe/jev-latest no OpenRouter).

Arquitetura Híbrida Inteligente:
1. JEV seleciona a ferramenta correta e os parâmetros discretos (alternativas) em 1 único passo (~200ms).
2. Se a ferramenta escolhida exigir parâmetros de texto aberto (ex: nome de evento, célula),
   utiliza uma chamada cirúrgica ao modelo do próprio agente (agent.model) para extração pontual (~150ms).
3. Executa o MCP diretamente via MCPToolExecutor.
4. Caso o JEV seja inconclusivo ou retorne 'nenhuma', o fluxo faz fallback automático para o ReAct comum.
"""

import os
import re
import json
import time
import logging
from typing import Optional, Dict, Any, List
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.models.agent import Agent
from app.models.mcp import MCP
from app.services.mcp_tools import MCPToolExecutor, _extract_from_ai_params

logger = logging.getLogger(__name__)


class JevDispatcherService:
    def __init__(self, db: AsyncSession, context_data: Optional[Dict[str, Any]] = None):
        self.db = db
        self.context_data = context_data or {}
        self.api_key = (
            getattr(settings, "OPENROUTER_API_KEY", None)
            or os.environ.get("OPENROUTER_API_KEY", "")
        ).strip()

    async def dispatch(
        self,
        agent: Agent,
        message: str,
        orientation: str = "",
        context_data: Optional[Dict[str, Any]] = None,
        response_style: str = "structured",
    ) -> Optional[str]:
        """
        Roteia a mensagem do usuário dinamicamente para as ferramentas do agente via TypeSafe JEV.
        Retorna a resposta pronta ou None para ativar fallback transparente ao motor padrão.
        """
        if not self.api_key:
            logger.warning("[JevDispatcher] ⚠️ OPENROUTER_API_KEY não encontrada. Fallback para motor padrão.")
            return None

        merged_context = {**self.context_data, **(context_data or {})}
        executor = MCPToolExecutor(self.db, context_data=merged_context)

        # 1. Carregar MCPs vinculados ao agente
        agent_mcps = await executor.get_agent_mcps(str(agent.id))
        if not agent_mcps:
            logger.info(f"[JevDispatcher] Agente '{agent.name}' não possui MCPs ativos. Fallback.")
            return None

        full_query = f"{orientation} {message}".strip()
        t0 = time.perf_counter()

        try:
            # 2. Mapeamento dinâmico de ferramentas para o JEV
            tool_map = {}
            tool_criteria = {}

            for mcp in agent_mcps:
                # Chave limpa e única para o JEV
                safe_key = re.sub(r'[^a-zA-Z0-9_]', '_', mcp.name).strip('_')[:64]
                tool_map[safe_key] = mcp
                desc = (mcp.description or mcp.name).strip()
                # Limite seguro para cada critério
                tool_criteria[safe_key] = desc[:250]

            tool_criteria["nenhuma"] = "Nenhuma das ferramentas se aplica a esta solicitação"

            # 3. Montagem das Perguntas do JEV (Tool + Filtros Discretos Comuns)
            questions: Dict[str, Any] = {
                "ferramenta_alvo": {
                    "type": "choice",
                    "instructions": f"Qual das ferramentas do agente '{agent.name}' deve ser executada para atender a solicitação?",
                    "criteria": tool_criteria
                },
                "filtro_tempo": {
                    "type": "choice",
                    "instructions": "Se a solicitação envolve período ou data, qual filtro de tempo foi indicado?",
                    "criteria": {
                        "month": "Mês atual ou padrão se não especificado",
                        "day": "Dia de hoje",
                        "week": "Semana atual",
                        "last_month": "Mês passado",
                        "last_three_months": "Últimos 3 meses",
                        "nenhum": "Nenhum filtro de período específico"
                    }
                }
            }

            # 4. Montagem do Contexto (State) contemplando o PROMPT do Agente
            state = (
                f"DIRETRIZES E REGRAS DO AGENTE ({agent.name}):\n"
                f"{agent.system_prompt or ''}\n\n"
                f"SOLICITAÇÃO DO USUÁRIO / COORDENADOR:\n"
                f"{full_query}"
            ).strip()

            # 5. Execução da Decisão no TypeSafe JEV
            decision = await self._call_jev_decision(state=state, questions=questions)
            if not decision:
                logger.info(f"[JevDispatcher] JEV sem resposta. Ativando fallback para '{agent.name}'.")
                return None

            tool_choice = decision.get("ferramenta_alvo", {}).get("choice")
            tool_conf = decision.get("ferramenta_alvo", {}).get("confidence", 0.0)
            time_filter = decision.get("filtro_tempo", {}).get("choice", "month")

            elapsed_jev = (time.perf_counter() - t0) * 1000
            logger.info(
                f"[JevDispatcher] ⚡ JEV selecionou '{tool_choice}' (conf={tool_conf}) "
                f"filtro='{time_filter}' em {elapsed_jev:.1f}ms"
            )

            if not tool_choice or tool_choice == "nenhuma" or tool_conf < 0.5:
                logger.info(f"[JevDispatcher] Escolha inconclusiva ou 'nenhuma' ({tool_choice}). Ativando fallback.")
                return None

            selected_mcp = tool_map.get(tool_choice)
            if not selected_mcp:
                logger.warning(f"[JevDispatcher] Tool '{tool_choice}' não encontrada no mapa local.")
                return None

            # 6. Descoberta e Resolução Híbrida de Parâmetros
            tool_args = await self._resolve_parameters(
                mcp=selected_mcp,
                query=full_query,
                time_filter=time_filter,
                agent_model=getattr(agent, "model", None) or "deepseek/deepseek-v4.1-flash"
            )

            # 7. Execução do MCP via MCPToolExecutor
            langchain_tools = await executor.create_langchain_tools(selected_mcp)
            if not langchain_tools:
                logger.error(f"[JevDispatcher] Falha ao criar LangChain Tool para MCP '{selected_mcp.name}'.")
                return None

            tool_runner = langchain_tools[0]
            logger.info(f"[JevDispatcher] 🚀 Executando '{selected_mcp.name}' com args: {tool_args}")
            raw_result = await tool_runner.ainvoke(tool_args)

            # 8. Formatação final de retorno
            formatted_response = self._format_result(
                agent_name=agent.name,
                mcp_name=selected_mcp.name,
                raw_result=raw_result,
                response_style=response_style
            )

            total_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[JevDispatcher] ✅ Agente '{agent.name}' despachado via JEV com sucesso em {total_ms:.1f}ms")
            return formatted_response

        except Exception as e:
            import traceback
            logger.error(f"[JevDispatcher] ❌ Exceção ao despachar via JEV para '{agent.name}': {e}")
            logger.error(traceback.format_exc())
            return None

    async def _call_jev_decision(self, state: str, questions: dict) -> Optional[dict]:
        """Faz a requisição para a API de Decisions do OpenRouter com o modelo TypeSafe JEV."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://basileia.global",
            "X-Title": "Basileia IA"
        }
        payload = {
            "model": "~typesafe/jev-latest",
            "state": state,
            "questions": questions
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(
                    "https://openrouter.ai/api/alpha/decisions",
                    headers=headers,
                    json=payload
                )
                if res.status_code == 200:
                    data = res.json()
                    return data.get("answers", data)
                else:
                    logger.warning(f"[JevDispatcher] OpenRouter JEV erro HTTP {res.status_code}: {res.text[:200]}")
                    return None
        except Exception as e:
            logger.warning(f"[JevDispatcher] Erro de rede ao conectar com JEV: {e}")
            return None

    async def _resolve_parameters(
        self,
        mcp: MCP,
        query: str,
        time_filter: str,
        agent_model: str
    ) -> Dict[str, Any]:
        """
        Resolve os parâmetros requeridos pelo MCP:
        - Se for filtro temporal discreto, preenche a partir da decisão do JEV.
        - Se for texto aberto (nome de célula, evento, pessoa), extrai cirurgicamente com o modelo do agente.
        """
        import urllib.parse
        tool_args: Dict[str, Any] = {}

        # Extrair todos os $fromAI definidos no MCP
        ai_params = {}
        if mcp.endpoint:
            ai_params.update(_extract_from_ai_params(urllib.parse.unquote(mcp.endpoint)))
        if mcp.headers:
            ai_params.update(_extract_from_ai_params(json.dumps(mcp.headers)))
        if mcp.body_template:
            ai_params.update(_extract_from_ai_params(json.dumps(mcp.body_template)))
        query_tpl = getattr(mcp, "query_template", {}) or {}
        if query_tpl:
            ai_params.update(_extract_from_ai_params(json.dumps(query_tpl)))

        for p_name, p_info in ai_params.items():
            desc = p_info.get("description", "").lower()

            # Caso 1: Parâmetro com alternativas de período / filtro de data
            if p_name in ["filter", "periodo", "filtro"] or any(k in desc for k in ["mês", "mes", "semana", "dia", "month", "week", "day"]):
                if "current_month" in desc:
                    if time_filter == "last_month":
                        tool_args[p_name] = "last_month"
                    elif time_filter == "last_three_months":
                        tool_args[p_name] = "last_three_months"
                    else:
                        tool_args[p_name] = "current_month"
                else:
                    # Filtros normais: month, week, day
                    if time_filter in ["month", "week", "day"]:
                        tool_args[p_name] = time_filter
                    else:
                        tool_args[p_name] = "month"

            # Caso 2: Parâmetro de datas no formato ISO (start_date, end_date)
            elif p_name in ["start_date", "data_inicio"]:
                import datetime
                tool_args[p_name] = f"{datetime.date.today().isoformat()}T00:00:00"
            elif p_name in ["end_date", "data_fim"]:
                import datetime
                tool_args[p_name] = f"{datetime.date.today().isoformat()}T23:59:59"

            # Caso 3: Texto aberto (nome de evento, curso, célula, etc.)
            else:
                extracted_val = await self._extract_open_text_param(
                    query=query,
                    param_name=p_name,
                    param_desc=p_info.get("description", p_name),
                    model=agent_model
                )
                if extracted_val:
                    tool_args[p_name] = extracted_val

        return tool_args

    async def _extract_open_text_param(
        self,
        query: str,
        param_name: str,
        param_desc: str,
        model: str
    ) -> str:
        """
        Extração pontual e cirúrgica de texto aberto utilizando o modelo configurado no agente.
        Garante alta agilidade (~150-250ms) e consumo mínimo de tokens.
        """
        # 1. Regex de atalho para entidades comuns
        if any(k in param_name.lower() for k in ["cell", "celula"]):
            m = re.search(r'c[ée]lula\s+([A-Za-z0-9À-ÿ\s\-]+?)(?:\s*(?:\?|\.|,|$|hoje|ontem|nesse|neste))', query, re.IGNORECASE)
            if m and len(m.group(1).strip()) > 2:
                return m.group(1).strip()

        if any(k in param_name.lower() for k in ["event", "evento"]):
            m = re.search(r'evento\s+([A-Za-z0-9À-ÿ\s\-]+?)(?:\s*(?:\?|\.|,|$|hoje|ontem|nesse|neste))', query, re.IGNORECASE)
            if m and len(m.group(1).strip()) > 2:
                return m.group(1).strip()

        if any(k in param_name.lower() for k in ["course", "curso"]):
            m = re.search(r'curso\s+([A-Za-z0-9À-ÿ\s\-]+?)(?:\s*(?:\?|\.|,|$|hoje|ontem|nesse|neste))', query, re.IGNORECASE)
            if m and len(m.group(1).strip()) > 2:
                return m.group(1).strip()

        # 2. Chamada cirúrgica de 1 linha ao modelo do agente
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://basileia.global",
                "X-Title": "Basileia IA"
            }
            # Fallback seguro para DeepSeek v4.1 Flash se o modelo cadastrado não for compatível
            target_model = model if model and "/" in model else "deepseek/deepseek-v4.1-flash"
            prompt = (
                f"Da mensagem abaixo, extraia apenas o valor específico para o campo '{param_name}' ({param_desc}).\n"
                f"Se não for citado ou não souber, retorne exatamente 'VAZIO'.\n"
                f"Mensagem: \"{query}\"\n"
                f"Valor extraído:"
            )
            payload = {
                "model": target_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 30,
                "temperature": 0.0
            }
            async with httpx.AsyncClient(timeout=6.0) as client:
                res = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    choices = data.get("choices") or []
                    if choices:
                        raw_c = choices[0].get("message", {}).get("content")
                        if raw_c:
                            val = raw_c.strip().strip('"').strip("'")
                            if val and val != "VAZIO":
                                return val
        except Exception as e:
            logger.warning(f"[JevDispatcher] Extração pontual com {model} falhou: {e}")

        return ""

    def _format_result(
        self,
        agent_name: str,
        mcp_name: str,
        raw_result: Any,
        response_style: str
    ) -> str:
        """Formata o retorno da execução do MCP para o Orquestrador."""
        parsed_data = raw_result
        if isinstance(raw_result, str):
            try:
                parsed_data = json.loads(raw_result)
            except Exception:
                pass

        if response_style == "structured":
            structured_payload = {
                "achados": [f"Dados consultados com sucesso pela ferramenta '{mcp_name}' do agente '{agent_name}'."],
                "dados": parsed_data,
                "recomendacao": "Apresente estes dados ao usuário de forma clara, acolhedora e objetiva."
            }
            return json.dumps(structured_payload, ensure_ascii=False)
        else:
            if isinstance(parsed_data, (dict, list)):
                return json.dumps({"ferramenta": mcp_name, "dados": parsed_data}, ensure_ascii=False)
            return str(parsed_data)
