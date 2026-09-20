"""
JevDispatcherService — Roteador Genérico de Ferramentas via TypeSafe JEV
========================================================================
Permite que qualquer agente especialista com a configuração {"jev": true}
em seu config JSON execute suas ferramentas com ultra-baixa latência (~200ms)
utilizando TypeSafe JEV (~typesafe/jev-latest no OpenRouter).

Suporte a Execução Paralela (Batch) com {"jev_paralelo": true}:
- Quando o usuário pede uma visão consolidada ("todos", "resumo geral", "balanço"),
  o JEV aciona o modo paralelo.
- Todas as ferramentas de consulta (GET) ativas do agente são disparadas
  simultaneamente via asyncio.gather, terminando em ~300ms em vez de 9s.
- Ferramentas de escrita/mutação (POST, DELETE) continuam protegidas e só rodam
  em chamadas pontuais.
"""

import os
import re
import json
import time
import asyncio
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
        Suporta chamadas pontuais e execução consolidada paralela se jev_paralelo=true.
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

        # 2. Checar se modo paralelo está ativado no config do agente
        raw_agent_config = getattr(agent, "config", {}) or {}
        if isinstance(raw_agent_config, str):
            try:
                raw_agent_config = json.loads(raw_agent_config)
            except Exception:
                raw_agent_config = {}
        is_parallel_enabled = bool(raw_agent_config.get("jev_paralelo", False))

        full_query = f"{orientation} {message}".strip()
        t0 = time.perf_counter()

        try:
            # 3. Mapeamento dinâmico de ferramentas para o JEV
            tool_map = {}
            tool_criteria = {}

            for mcp in agent_mcps:
                safe_key = re.sub(r'[^a-zA-Z0-9_]', '_', mcp.name).strip('_')[:64]
                tool_map[safe_key] = mcp
                desc = (mcp.description or mcp.name).strip()
                tool_criteria[safe_key] = desc[:250]

            if is_parallel_enabled:
                tool_criteria["todas_ferramentas_resumo"] = (
                    "Executar todas as ferramentas de consulta/resumo em paralelo "
                    "(usar quando o usuário pede 'todos os relatórios', 'todos', 'resumo geral', "
                    "'balanço completo', 'panorama geral' ou visão consolidada de dados)"
                )

            tool_criteria["nenhuma"] = "Nenhuma das ferramentas se aplica a esta solicitação"

            # 4. Montagem das Perguntas do JEV (Tool + Filtros Discretos Comuns)
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

            # 5. Montagem do Contexto (State) contemplando o PROMPT do Agente
            state = (
                f"DIRETRIZES E REGRAS DO AGENTE ({agent.name}):\n"
                f"{agent.system_prompt or ''}\n\n"
                f"SOLICITAÇÃO DO USUÁRIO / COORDENADOR:\n"
                f"{full_query}"
            ).strip()

            # 6. Execução da Decisão no TypeSafe JEV
            decision = await self._call_jev_decision(state=state, questions=questions)
            
            # Atalho heurístico caso o JEV seja indeciso mas o usuário tenha pedido expressamente 'todos'
            query_clean = message.strip().lower()
            is_explicit_all = query_clean in ["todos", "todos os relatorios", "todos os relatórios", "tudo", "resumo geral", "ver todos"]

            if not decision and not (is_parallel_enabled and is_explicit_all):
                logger.info(f"[JevDispatcher] JEV sem resposta. Ativando fallback para '{agent.name}'.")
                return None

            tool_choice = decision.get("ferramenta_alvo", {}).get("choice") if decision else None
            tool_conf = decision.get("ferramenta_alvo", {}).get("confidence", 0.0) if decision else 0.0
            time_filter = decision.get("filtro_tempo", {}).get("choice", "month") if decision else "month"

            # Se for pedido explícito de 'todos' com jev_paralelo ativado, assume modo paralelo
            if is_parallel_enabled and (tool_choice == "todas_ferramentas_resumo" or is_explicit_all):
                logger.info(f"[JevDispatcher] ⚡ Modo PARALELO ativado para '{agent.name}'. Disparando ferramentas em lote.")
                return await self._dispatch_parallel(
                    agent=agent,
                    mcps=agent_mcps,
                    executor=executor,
                    query=full_query,
                    time_filter=time_filter,
                    response_style=response_style,
                    t0=t0
                )

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

            # 7. Descoberta e Resolução Híbrida de Parâmetros (Chamada Pontual)
            tool_args = await self._resolve_parameters(
                mcp=selected_mcp,
                query=full_query,
                time_filter=time_filter,
                agent_model=getattr(agent, "model", None) or "deepseek/deepseek-v4.1-flash"
            )

            # 8. Execução do MCP via MCPToolExecutor
            langchain_tools = await executor.create_langchain_tools(selected_mcp)
            if not langchain_tools:
                logger.error(f"[JevDispatcher] Falha ao criar LangChain Tool para MCP '{selected_mcp.name}'.")
                return None

            tool_runner = langchain_tools[0]
            logger.info(f"[JevDispatcher] 🚀 Executando '{selected_mcp.name}' com args: {tool_args}")
            raw_result = await tool_runner.ainvoke(tool_args)

            # 9. Formatação final de retorno
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

    async def _dispatch_parallel(
        self,
        agent: Agent,
        mcps: List[MCP],
        executor: MCPToolExecutor,
        query: str,
        time_filter: str,
        response_style: str,
        t0: float
    ) -> Optional[str]:
        """
        Executa todas as ferramentas de consulta (GET) em paralelo via asyncio.gather.
        Deduplica endpoints idênticos e consolida os dados com máxima velocidade (~300ms).
        """
        # Filtrar apenas ferramentas de LEITURA (GET) para segurança absoluta
        read_mcps = [m for m in mcps if str(getattr(m, "method", "GET")).upper() == "GET"]
        if not read_mcps:
            logger.warning(f"[JevDispatcher] Nenhuma ferramenta GET disponível para paralelo em '{agent.name}'.")
            return None

        # Deduplicação de endpoints duplicados/cópias
        seen_endpoints = set()
        unique_read_mcps = []
        for m in read_mcps:
            ep_key = f"{m.method}:{m.endpoint}"
            if ep_key not in seen_endpoints:
                seen_endpoints.add(ep_key)
                unique_read_mcps.append(m)

        agent_model = getattr(agent, "model", None) or "deepseek/deepseek-v4.1-flash"

        async def _execute_single(mcp_item: MCP):
            try:
                args = await self._resolve_parameters(
                    mcp=mcp_item,
                    query=query,
                    time_filter=time_filter,
                    agent_model=agent_model
                )
                tools = await executor.create_langchain_tools(mcp_item)
                if tools:
                    res = await tools[0].ainvoke(args)
                    if isinstance(res, str):
                        try:
                            res = json.loads(res)
                        except Exception:
                            pass
                    return mcp_item.name, res
            except Exception as err:
                logger.warning(f"[JevDispatcher] Falha na ferramenta paralela '{mcp_item.name}': {err}")
                return mcp_item.name, {"error": str(err)}
            return mcp_item.name, None

        logger.info(f"[JevDispatcher] ⚡ Disparando {len(unique_read_mcps)} ferramentas em paralelo via asyncio.gather...")
        parallel_results = await asyncio.gather(
            *[_execute_single(m) for m in unique_read_mcps],
            return_exceptions=True
        )

        consolidated_data = {}
        for item in parallel_results:
            if isinstance(item, tuple) and len(item) == 2:
                name, val = item
                consolidated_data[name] = val
            elif isinstance(item, Exception):
                logger.warning(f"[JevDispatcher] Exceção em tarefa paralela: {item}")

        total_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            f"[JevDispatcher] 🏁 Modo PARALELO concluído: {len(consolidated_data)} ferramentas "
            f"executadas em {total_ms:.1f}ms"
        )

        if response_style == "structured":
            structured_payload = {
                "achados": [
                    f"Relatório consolidado executado com sucesso em paralelo para o agente '{agent.name}'.",
                    f"Total de {len(consolidated_data)} consultas realizadas simultaneamente via JEV Paralelo."
                ],
                "dados": consolidated_data,
                "recomendacao": "Apresente um resumo completo e humanizado de todos os indicadores levantados."
            }
            return json.dumps(structured_payload, ensure_ascii=False)
        else:
            return json.dumps({"consolidado": True, "dados": consolidated_data}, ensure_ascii=False)

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

            if p_name in ["filter", "periodo", "filtro"] or any(k in desc for k in ["mês", "mes", "semana", "dia", "month", "week", "day"]):
                if "current_month" in desc:
                    if time_filter == "last_month":
                        tool_args[p_name] = "last_month"
                    elif time_filter == "last_three_months":
                        tool_args[p_name] = "last_three_months"
                    else:
                        tool_args[p_name] = "current_month"
                else:
                    if time_filter in ["month", "week", "day"]:
                        tool_args[p_name] = time_filter
                    else:
                        tool_args[p_name] = "month"

            elif p_name in ["start_date", "data_inicio"]:
                import datetime
                tool_args[p_name] = f"{datetime.date.today().isoformat()}T00:00:00"
            elif p_name in ["end_date", "data_fim"]:
                import datetime
                tool_args[p_name] = f"{datetime.date.today().isoformat()}T23:59:59"

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

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://basileia.global",
                "X-Title": "Basileia IA"
            }
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
