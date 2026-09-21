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

_SOLICITATION_TYPES_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}


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
                mcp_low = mcp.name.lower()
                if "register_solicitation" in mcp_low:
                    desc = "Cadastrar, criar ou registrar novo pedido de oração, solicitação de ajuda, falar com o pastor ou apoio"
                elif "get_all_solicitation_responsible" in mcp_low:
                    desc = "Listar solicitações ou pedidos que o usuário é responsável por atender (para líderes, pastores e equipe)"
                elif "get_all_solicitation" in mcp_low:
                    desc = "Listar as solicitações ou pedidos feitos pelo próprio usuário (meus pedidos, minhas orações, status de pedidos)"
                elif "list_solicitation_types" in mcp_low:
                    desc = "Listar os tipos ou categorias de solicitações disponíveis na igreja"
                elif "update_status_served" in mcp_low:
                    desc = "Marcar uma solicitação ou pedido como atendido ou concluído"
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

            elif p_name in ["presence_date", "data_presenca"]:
                import datetime
                q_lower = query.lower()
                today = datetime.date.today()
                if "ontem" in q_lower:
                    tool_args[p_name] = (today - datetime.timedelta(days=1)).isoformat()
                elif "hoje" in q_lower:
                    tool_args[p_name] = today.isoformat()
                else:
                    m_date = re.search(r'(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})', query)
                    if m_date:
                        d, m, y = m_date.groups()
                        tool_args[p_name] = f"{y}-{int(m):02d}-{int(d):02d}"
                    else:
                        m_short = re.search(r'(\d{1,2})[\/\-](\d{1,2})', query)
                        if m_short:
                            d, m = m_short.groups()
                            tool_args[p_name] = f"{today.year}-{int(m):02d}-{int(d):02d}"
                        else:
                            extracted_val = await self._extract_open_text_param(
                                query=query,
                                param_name=p_name,
                                param_desc=p_info.get("description", p_name),
                                model=agent_model
                            )
                            if extracted_val:
                                m_conv = re.search(r'(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})', extracted_val)
                                if m_conv:
                                    d, m, y = m_conv.groups()
                                    tool_args[p_name] = f"{y}-{int(m):02d}-{int(d):02d}"
                                elif re.match(r'^\d{4}-\d{2}-\d{2}$', extracted_val):
                                    tool_args[p_name] = extracted_val
                                else:
                                    tool_args[p_name] = today.isoformat()
                            else:
                                tool_args[p_name] = today.isoformat()

            else:
                extracted_val = await self._extract_open_text_param(
                    query=query,
                    param_name=p_name,
                    param_desc=p_info.get("description", p_name),
                    model=agent_model
                )
                if extracted_val:
                    tool_args[p_name] = extracted_val

        # Fallback de cell_id via context_data se não resolvido
        if "cell_id" in ai_params and "cell_id" not in tool_args:
            ctx_cids = self.context_data.get("member", {}).get("cell_ids", [])
            first_cid = ctx_cids[0] if isinstance(ctx_cids, list) and ctx_cids else None
            ctx_cell_id = (
                self.context_data.get("cell_id")
                or self.context_data.get("cell", {}).get("_id")
                or self.context_data.get("member", {}).get("cell_id")
                or first_cid
            )
            if ctx_cell_id and re.match(r'^[a-fA-F0-9]{24}$', str(ctx_cell_id)):
                tool_args["cell_id"] = str(ctx_cell_id)

        # Resolução especializada para ferramentas de presença de célula
        mcp_name_lower = getattr(mcp, "name", "").lower()
        if "register_cell_attendance_list" in mcp_name_lower or "presence" in getattr(mcp, "endpoint", "").lower():
            await self._resolve_cell_attendance_parameters(
                mcp=mcp,
                query=query,
                tool_args=tool_args,
                agent_model=agent_model
            )

        # Resolução especializada para ferramentas de busca de células próximas
        if (
            "cell_near_residence" in mcp_name_lower
            or "near_residence" in getattr(mcp, "endpoint", "").lower()
            or ("near" in mcp_name_lower and "cell" in mcp_name_lower)
            or ("celula" in mcp_name_lower and "perto" in mcp_name_lower)
        ):
            self._resolve_cell_near_parameters(
                mcp=mcp,
                query=query,
                tool_args=tool_args
            )

        # Resolução especializada para ferramentas de solicitações / pedidos de oração
        if (
            "solicit" in mcp_name_lower
            or "pedido" in mcp_name_lower
            or "oracao" in mcp_name_lower
            or "oração" in mcp_name_lower
        ):
            await self._resolve_solicitation_parameters(
                mcp=mcp,
                query=query,
                tool_args=tool_args,
                agent_model=agent_model
            )

        return tool_args

    async def _resolve_cell_attendance_parameters(
        self,
        mcp: MCP,
        query: str,
        tool_args: Dict[str, Any],
        agent_model: str
    ) -> None:
        """
        Resolve deterministicamente os parâmetros necessários para cadastro de presença de célula:
        1. cell_id (garante ObjectId válido da célula)
        2. presence_date (garante formato YYYY-MM-DD para 'ontem', 'hoje' ou data mencionada)
        3. members_and_members_visitors (mapeia nomes de ausentes e presentes para IDs reais de membros/visitantes)
        """
        import datetime
        import unicodedata

        def _norm(s: str) -> str:
            if not s:
                return ""
            s_clean = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('ASCII')
            return s_clean.lower().strip()

        q_lower = query.lower()
        today = datetime.date.today()

        # 1. Resolver presence_date se ainda não estiver formatado em YYYY-MM-DD
        cur_date = tool_args.get("presence_date")
        if not cur_date or not re.match(r'^\d{4}-\d{2}-\d{2}$', str(cur_date)):
            if "ontem" in q_lower:
                tool_args["presence_date"] = (today - datetime.timedelta(days=1)).isoformat()
            elif "hoje" in q_lower:
                tool_args["presence_date"] = today.isoformat()
            else:
                m_date = re.search(r'(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})', query)
                if m_date:
                    d, m, y = m_date.groups()
                    tool_args["presence_date"] = f"{y}-{int(m):02d}-{int(d):02d}"
                else:
                    tool_args["presence_date"] = today.isoformat()

        # 2. Resolver cell_id se não for hex de 24 caracteres
        cur_cid = tool_args.get("cell_id")
        valid_cid = False
        if cur_cid and isinstance(cur_cid, str) and re.match(r'^[a-fA-F0-9]{24}$', cur_cid):
            valid_cid = True

        phone = (
            self.context_data.get("member", {}).get("phone")
            or self.context_data.get("system", {}).get("phone")
            or self.context_data.get("system", {}).get("user_phone")
            or self.context_data.get("global", {}).get("phone")
        )
        church_id = (
            self.context_data.get("church", {}).get("_id")
            or self.context_data.get("member", {}).get("church_id")
        )
        apikey = (
            self.context_data.get("system", {}).get("apikey")
            or self.context_data.get("global", {}).get("apikey")
        )
        base_url = (
            self.context_data.get("system", {}).get("baseUrlBasileia")
            or self.context_data.get("global", {}).get("baseUrlBasileia")
            or "https://dash.basileia.global"
        ).rstrip("/")

        cell_data = None
        cur_members = tool_args.get("members_and_members_visitors")
        needs_members = not cur_members or not re.search(r'[a-fA-F0-9]{24}', str(cur_members))

        if not valid_cid or needs_members:
            if phone and church_id:
                try:
                    headers = {"Authorization": f"Bearer {apikey}"} if apikey else {}
                    async with httpx.AsyncClient(timeout=8.0) as client:
                        resp = await client.get(
                            f"{base_url}/api/cells/n8n/{phone}?church_id={church_id}",
                            headers=headers
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            cells = data.get("body", []) if isinstance(data, dict) else data
                            if isinstance(cells, list) and cells:
                                selected_cell = cells[0]
                                for c in cells:
                                    cname = c.get("name", "")
                                    if cname and _norm(cname) in _norm(query):
                                        selected_cell = c
                                        break
                                cell_data = selected_cell
                                if not valid_cid and selected_cell.get("_id"):
                                    tool_args["cell_id"] = selected_cell["_id"]
                                    valid_cid = True
                except Exception as e:
                    logger.warning(f"[JevDispatcher] Aviso ao buscar células do líder: {e}")

        if not valid_cid:
            ctx_cids = self.context_data.get("member", {}).get("cell_ids", [])
            if ctx_cids and isinstance(ctx_cids, list) and re.match(r'^[a-fA-F0-9]{24}$', str(ctx_cids[0])):
                tool_args["cell_id"] = str(ctx_cids[0])
                valid_cid = True

        # 3. Resolver members_and_members_visitors mapeando nomes para IDs
        if needs_members:
            member_list = []
            if cell_data and isinstance(cell_data.get("member_or_visitant"), list):
                member_list = cell_data["member_or_visitant"]
            elif valid_cid and phone and church_id:
                try:
                    headers = {"Authorization": f"Bearer {apikey}"} if apikey else {}
                    async with httpx.AsyncClient(timeout=8.0) as client:
                        resp = await client.get(
                            f"{base_url}/api/cell/members/n8n/{phone}?cell_id={tool_args['cell_id']}&church_id={church_id}",
                            headers=headers
                        )
                        if resp.status_code == 200:
                            m_json = resp.json()
                            member_list = m_json.get("members", []) if isinstance(m_json, dict) else m_json
                except Exception as e:
                    logger.warning(f"[JevDispatcher] Aviso ao buscar membros da célula: {e}")

            if member_list:
                q_norm = _norm(query)
                absent_section = ""
                absent_patterns = [
                    r'(?:ausentes|faltaram|faltou|faltas|nao compareceram|nao vieram|ausente)(?: foram| sao|:)?\s*([^.]+)',
                    r'([^.]+?)(?:faltaram|faltou|nao compareceram|nao vieram)'
                ]
                for pat in absent_patterns:
                    m_abs = re.search(pat, q_norm)
                    if m_abs:
                        absent_section = m_abs.group(1)
                        break

                presents = []
                absents = []
                for m_item in member_list:
                    role = m_item.get("role")
                    if role not in ["member", "member_visitant"]:
                        continue

                    m_id = m_item.get("_id")
                    if not m_id:
                        continue

                    fname = m_item.get("fullname", "").strip()
                    fn_norm = _norm(fname)
                    parts = fn_norm.split()
                    first_name = parts[0] if parts else ""

                    is_absent = False
                    if absent_section:
                        if fn_norm and fn_norm in absent_section:
                            is_absent = True
                        elif first_name and len(first_name) >= 3 and re.search(r'\b' + re.escape(first_name) + r'\b', absent_section):
                            is_absent = True

                    if is_absent:
                        absents.append(fname)
                    else:
                        presents.append(m_item)

                if presents:
                    present_ids = [p["_id"] for p in presents]
                    tool_args["members_and_members_visitors"] = ",".join(present_ids)
                    logger.info(
                        f"[JevDispatcher] Mapeamento de presença da célula concluído: "
                        f"{len(present_ids)} presentes ({len(absents)} ausentes: {absents})"
                    )

    def _resolve_cell_near_parameters(
        self,
        mcp: MCP,
        query: str,
        tool_args: Dict[str, Any]
    ) -> None:
        """
        Resolve deterministicamente os parâmetros para busca de célula próxima à residência:
        - CEP (do query ou fallback para context_data['member']['address'])
        - address (do query ou fallback formatado de context_data['member']['address'])
        - distance (do query ou default 5)
        Garante que tool_args['CEP'] e tool_args['address'] existam como strings (nunca None).
        """
        # 1. Distância
        m_dist = re.search(r'(\d+)\s*(?:km|quil[oô]metros)', query, re.IGNORECASE)
        if m_dist:
            try:
                tool_args["distance"] = int(m_dist.group(1))
            except Exception:
                tool_args["distance"] = 5
        elif "distance" not in tool_args:
            tool_args["distance"] = 5

        # 2. CEP informado na query
        query_cep = None
        m_cep = re.search(r'\b(\d{5})[-]?(\d{3})\b', query)
        if m_cep:
            query_cep = f"{m_cep.group(1)}{m_cep.group(2)}"
        else:
            m_cep8 = re.search(r'\bcep\s*[:=]?\s*(\d{8})\b', query, re.IGNORECASE)
            if m_cep8:
                query_cep = m_cep8.group(1)

        # 3. Endereço informado na query
        query_addr = None
        prefix_match = re.search(
            r'(?:endereço|endereco|moro na|moro no|moro em|fica na|fica no|localizada na|na rua|no bairro|no endereço|no endereco)\s*[:=]?\s*(.+)',
            query,
            re.IGNORECASE
        )
        if prefix_match:
            candidate = prefix_match.group(1).strip().rstrip('?.! ')
            if re.search(r'na rua\s*$', query[:prefix_match.start(1)], re.IGNORECASE) and not re.match(r'^(?:rua|r\.|av|avenida)\b', candidate, re.IGNORECASE):
                candidate = f"Rua {candidate}"
            if len(candidate) >= 4 and not re.match(r'^\d{5}[-]?\d{3}$', candidate):
                query_addr = candidate

        if not query_addr:
            street_match = re.search(
                r'\b((?:rua|r\.|av\.|avenida|travessa|trav\.|alameda|al\.|rodovia|rod\.|estrada|servidão|serv\.)\b.+)',
                query,
                re.IGNORECASE
            )
            if street_match:
                candidate = street_match.group(1).strip().rstrip('?.! ')
                if len(candidate) >= 4:
                    query_addr = candidate

        # 4. Contexto do membro caso query não tenha CEP nem endereço
        ctx_addr_raw = (
            self.context_data.get("member", {}).get("address")
            or self.context_data.get("address")
            or self.context_data.get("user", {}).get("address")
        )

        ctx_cep = None
        ctx_formatted_addr = None

        if isinstance(ctx_addr_raw, dict):
            ctx_cep = ctx_addr_raw.get("zip_code") or ctx_addr_raw.get("cep") or ctx_addr_raw.get("postal_code")
            parts = []
            st = ctx_addr_raw.get("street") or ctx_addr_raw.get("logradouro") or ctx_addr_raw.get("address")
            num = ctx_addr_raw.get("number") or ctx_addr_raw.get("numero")
            nb = ctx_addr_raw.get("neighborhood") or ctx_addr_raw.get("bairro")
            ci = ctx_addr_raw.get("city") or ctx_addr_raw.get("cidade")
            uf = ctx_addr_raw.get("state") or ctx_addr_raw.get("uf")
            if st: parts.append(str(st))
            if num: parts.append(str(num))
            if nb: parts.append(str(nb))
            if ci: parts.append(str(ci))
            if uf: parts.append(str(uf))
            if parts:
                ctx_formatted_addr = ", ".join(parts)
        elif isinstance(ctx_addr_raw, str) and ctx_addr_raw.strip():
            ctx_formatted_addr = ctx_addr_raw.strip()
            m_c = re.search(r'\b(\d{5})[-]?(\d{3})\b', ctx_formatted_addr)
            if m_c:
                ctx_cep = f"{m_c.group(1)}{m_c.group(2)}"

        if not ctx_cep:
            ctx_cep = self.context_data.get("member", {}).get("zip_code") or self.context_data.get("member", {}).get("cep")

        # 5. Decisão de preenchimento
        if query_cep:
            tool_args["CEP"] = query_cep
            tool_args["address"] = query_addr or ""
        elif query_addr:
            tool_args["CEP"] = ""
            tool_args["address"] = query_addr
        elif ctx_cep:
            tool_args["CEP"] = str(ctx_cep).replace("-", "").strip()
            tool_args["address"] = ctx_formatted_addr or ""
        elif ctx_formatted_addr:
            tool_args["CEP"] = ""
            tool_args["address"] = ctx_formatted_addr
        else:
            tool_args.setdefault("CEP", "")
            tool_args.setdefault("address", "")

        # Garantir chaves presentes e strings não-nulas
        if not tool_args.get("CEP"):
            tool_args["CEP"] = ""
        if not tool_args.get("address"):
            tool_args["address"] = ""

        logger.info(
            f"[JevDispatcher] 📍 Parâmetros de cell_near resolvidos: "
            f"CEP={tool_args.get('CEP')!r}, address={tool_args.get('address')!r}, distance={tool_args.get('distance')!r}"
        )

    async def _resolve_solicitation_parameters(
        self,
        mcp: MCP,
        query: str,
        tool_args: Dict[str, Any],
        agent_model: str
    ) -> None:
        """
        Resolve deterministicamente os parâmetros para ferramentas de Solicitações / Pedidos:
        1. church_id: garante _id da igreja presente
        2. type_id: busca tipos da igreja (com cache em memória), casa com o assunto (oração, pastor, cesta básica)
        3. subject: preenche assunto coerente com o tipo ou com o texto do usuário
        4. description: preenche mensagem detalhada do usuário
        5. solicitation_id: para consultas pontuais, update ou served, localiza o ID da solicitação aberta
        """
        import unicodedata

        def _norm(s: str) -> str:
            if not s:
                return ""
            s_clean = unicodedata.normalize('NFKD', str(s)).encode('ASCII', 'ignore').decode('ASCII')
            return s_clean.lower().strip()

        mcp_name_lower = getattr(mcp, "name", "").lower()
        endpoint_lower = getattr(mcp, "endpoint", "").lower()

        phone = (
            self.context_data.get("member", {}).get("phone")
            or self.context_data.get("system", {}).get("phone")
            or self.context_data.get("system", {}).get("user_phone")
            or self.context_data.get("global", {}).get("phone")
        )
        church_id = (
            self.context_data.get("church", {}).get("_id")
            or self.context_data.get("member", {}).get("church_id")
        )
        apikey = (
            self.context_data.get("system", {}).get("apikey")
            or self.context_data.get("global", {}).get("apikey")
        )
        base_url = (
            self.context_data.get("system", {}).get("baseUrlBasileia")
            or self.context_data.get("global", {}).get("baseUrlBasileia")
            or "https://dash.basileia.global"
        ).rstrip("/")

        if church_id and not tool_args.get("church_id"):
            tool_args["church_id"] = str(church_id)

        is_register = "register" in mcp_name_lower or "cadastro" in mcp_name_lower or "criar" in mcp_name_lower
        is_served = "served" in mcp_name_lower or "atendido" in mcp_name_lower or "served" in endpoint_lower
        is_update = "update" in mcp_name_lower and not is_served
        is_remove = "remove" in mcp_name_lower or "delete" in mcp_name_lower
        is_get_single = "get_solicitation" in mcp_name_lower and "all" not in mcp_name_lower and "responsible" not in mcp_name_lower

        # 1. Se for REGISTRO DE SOLICITAÇÃO (ex: Pedido de Oração, Falar com o Pastor, etc.)
        if is_register:
            types_list = []
            now = time.time()
            cid_str = str(church_id) if church_id else "default"
            if cid_str in _SOLICITATION_TYPES_CACHE:
                cached_time, cached_types = _SOLICITATION_TYPES_CACHE[cid_str]
                if now - cached_time < 3600:
                    types_list = cached_types

            if not types_list and phone and church_id:
                try:
                    headers = {"Authorization": f"Bearer {apikey}"} if apikey else {}
                    async with httpx.AsyncClient(timeout=8.0) as client:
                        resp = await client.get(
                            f"{base_url}/api/solicitation/types/n8n/{phone}?church_id={church_id}",
                            headers=headers
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            types_list = data.get("body", []) if isinstance(data, dict) else data
                            if isinstance(types_list, list) and types_list:
                                _SOLICITATION_TYPES_CACHE[cid_str] = (now, types_list)
                except Exception as err:
                    logger.warning(f"[JevDispatcher] Falha ao consultar tipos de solicitação: {err}")

            # Identificar o tipo ideal baseado na mensagem
            q_norm = _norm(query)
            selected_type = None

            if types_list and isinstance(types_list, list):
                # Heurística 1: Falar com o Pastor / Pastoral / Gabinete
                if any(w in q_norm for w in ["pastor", "pastoral", "conselho", "aconselhamento", "conversa", "conversar", "gabinete", "visita"]):
                    for t in types_list:
                        t_norm = _norm(t.get("description") or t.get("name") or "")
                        if any(w in t_norm for w in ["pastor", "pastoral", "visita", "atendimento", "gabinete", "aconselhamento"]):
                            selected_type = t
                            break

                # Heurística 2: Cesta Básica / Assistência Social / Alimento
                if not selected_type and any(w in q_norm for w in ["cesta", "alimento", "comida", "social", "ajuda financeira", "cesta basica"]):
                    for t in types_list:
                        t_norm = _norm(t.get("description") or t.get("name") or "")
                        if any(w in t_norm for w in ["cesta", "social", "alimento", "ajuda"]):
                            selected_type = t
                            break

                # Heurística 3: Pedido de Oração / Intercessão / Saúde / Cura / Família
                if not selected_type and any(w in q_norm for w in ["orac", "orar", "rezar", "intercess", "clamor", "cura", "saude", "vida", "familia", "libertacao"]):
                    for t in types_list:
                        t_norm = _norm(t.get("description") or t.get("name") or "")
                        if "orac" in t_norm:
                            selected_type = t
                            break

                # Heurística 4: Comparação direta com o nome/descrição de cada tipo
                if not selected_type:
                    for t in types_list:
                        t_norm = _norm(t.get("description") or t.get("name") or "")
                        if t_norm and t_norm in q_norm:
                            selected_type = t
                            break

                # Fallback: Tipo de Oração ou Primeiro tipo da lista
                if not selected_type:
                    for t in types_list:
                        t_norm = _norm(t.get("description") or t.get("name") or "")
                        if "orac" in t_norm:
                            selected_type = t
                            break
                    if not selected_type and types_list:
                        selected_type = types_list[0]

            if selected_type and isinstance(selected_type, dict):
                tid = selected_type.get("_id") or selected_type.get("id")
                if tid:
                    tool_args["type_id"] = str(tid)
                tname = selected_type.get("description") or selected_type.get("name") or "Pedido de Oração"
                if isinstance(tname, list):
                    tname = tname[0] if tname else "Pedido de Oração"
                if not tool_args.get("subject"):
                    tool_args["subject"] = str(tname).strip()

            # Resolver Subject / Assunto se não veio
            if not tool_args.get("subject"):
                if any(w in q_norm for w in ["pastor", "pastoral", "conselho"]):
                    tool_args["subject"] = "Atendimento Pastoral"
                elif any(w in q_norm for w in ["cesta", "alimento"]):
                    tool_args["subject"] = "Pedido de Cesta Básica"
                else:
                    tool_args["subject"] = "Pedido de Oração"

            # Resolver Description / Descrição
            if not tool_args.get("description"):
                clean_desc = re.sub(r'^(?:por favor|registre|cadastre|anote|abra uma solicitacao|solicito|gostaria de pedir|quero pedir)\s*', '', query, flags=re.IGNORECASE).strip()
                tool_args["description"] = clean_desc if len(clean_desc) > 3 else query.strip()

            logger.info(
                f"[JevDispatcher] 📝 Solicitação resolvida: type_id={tool_args.get('type_id')!r}, "
                f"subject={tool_args.get('subject')!r}, desc_len={len(str(tool_args.get('description', '')))}"
            )

        # 2. Se for UPDATE, ATENDIDO, REMOÇÃO ou GET_SINGLE, precisamos de solicitation_id
        if is_served or is_update or is_remove or is_get_single:
            cur_sid = (
                tool_args.get("solicitation_id")
                or tool_args.get("SOLICITACAO_ID")
                or self.context_data.get("solicitation_id")
            )
            # Buscar ID de 24 hex chars na query
            if not cur_sid or not re.match(r'^[a-fA-F0-9]{24}$', str(cur_sid)):
                m_hex = re.search(r'\b([a-fA-F0-9]{24})\b', query)
                if m_hex:
                    cur_sid = m_hex.group(1)

            # Se não encontrou ID explícito, mas o usuário quer marcar como atendido / atualizar
            if not cur_sid and phone and church_id:
                try:
                    headers = {"Authorization": f"Bearer {apikey}"} if apikey else {}
                    async with httpx.AsyncClient(timeout=8.0) as client:
                        resp = await client.get(
                            f"{base_url}/api/solicitations/n8n/{phone}?church_id={church_id}",
                            headers=headers
                        )
                        if resp.status_code == 200:
                            s_data = resp.json()
                            s_items = s_data.get("body", []) if isinstance(s_data, dict) else s_data
                            if isinstance(s_items, list) and s_items:
                                # Prioriza pedidos abertos (status == 0)
                                open_items = [s for s in s_items if s.get("status") == 0]
                                target = open_items[0] if open_items else s_items[0]
                                if target.get("_id"):
                                    cur_sid = target["_id"]
                except Exception as err:
                    logger.warning(f"[JevDispatcher] Falha ao localizar solicitação ativa do usuário: {err}")

            if cur_sid:
                tool_args["solicitation_id"] = str(cur_sid)
                tool_args["SOLICITACAO_ID"] = str(cur_sid)

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
        # Hexadecimal Mongo ObjectId (24 chars) para cell_id ou member_id
        if any(k in param_name.lower() for k in ["cell_id", "member_id", "_id"]):
            m_hex = re.search(r'\b[a-fA-F0-9]{24}\b', query)
            if m_hex:
                return m_hex.group(0)
            return ""

        # CEP numérico
        if "cep" in param_name.lower():
            m_cep = re.search(r'\b(\d{5})[-]?(\d{3})\b', query)
            if m_cep:
                try:
                    return int(f"{m_cep.group(1)}{m_cep.group(2)}")
                except Exception:
                    return f"{m_cep.group(1)}{m_cep.group(2)}"
            return ""

        # Endereço / Logradouro / Rua
        if any(k in param_name.lower() for k in ["address", "endereco", "endereço", "rua", "logradouro"]):
            prefix_match = re.search(
                r'(?:endereço|endereco|moro na|moro no|moro em|fica na|fica no|localizada na|na rua|no bairro|no endereço|no endereco)\s*[:=]?\s*(.+)',
                query,
                re.IGNORECASE
            )
            if prefix_match:
                candidate = prefix_match.group(1).strip().rstrip('?.! ')
                if re.search(r'na rua\s*$', query[:prefix_match.start(1)], re.IGNORECASE) and not re.match(r'^(?:rua|r\.|av|avenida)\b', candidate, re.IGNORECASE):
                    candidate = f"Rua {candidate}"
                if len(candidate) >= 4 and not re.match(r'^\d{5}[-]?\d{3}$', candidate):
                    return candidate

            street_match = re.search(
                r'\b((?:rua|r\.|av\.|avenida|travessa|trav\.|alameda|al\.|rodovia|rod\.|estrada|servidão|serv\.)\b.+)',
                query,
                re.IGNORECASE
            )
            if street_match:
                candidate = street_match.group(1).strip().rstrip('?.! ')
                if len(candidate) >= 4:
                    return candidate

        # Celular
        if any(k in param_name.lower() for k in ["cellphone", "telefone", "celular", "phone"]):
            m_phone = re.search(r'\b(?:55)?(?:\d{2})?(?:9\d{8})\b', re.sub(r'[\s\(\)\-]', '', query))
            if m_phone:
                return m_phone.group(0)

        # Nome de pessoa / visitante
        if any(k in param_name.lower() for k in ["fullname", "nome"]):
            m_fn = re.search(r'(?:visitante|membro|nome(?:\s+do\s+visitante)?)\s*[:=]?\s*([A-Za-zÀ-ÿ\s]{3,40})', query, re.IGNORECASE)
            if m_fn and len(m_fn.group(1).strip()) > 2:
                return m_fn.group(1).strip()

        if any(k in param_name.lower() for k in ["cell_name", "nome_celula"]) and not param_name.endswith("_id"):
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
            if "register_cell_attendance_list" in mcp_name.lower():
                msg_body = parsed_data.get("body", "") if isinstance(parsed_data, dict) else str(parsed_data)
                structured_payload = {
                    "achados": [
                        "A lista de presença da célula foi cadastrada com sucesso no sistema.",
                        f"Retorno do servidor: {msg_body}"
                    ],
                    "dados": parsed_data,
                    "recomendacao": "Confirme amigavelmente ao líder que a presença da sua célula foi lançada e registrada com sucesso."
                }
                return json.dumps(structured_payload, ensure_ascii=False)

            if "cell_near" in mcp_name.lower() or "near_residence" in mcp_name.lower() or "perto" in mcp_name.lower():
                cells = []
                if isinstance(parsed_data, list):
                    cells = parsed_data
                elif isinstance(parsed_data, dict) and isinstance(parsed_data.get("celulas"), list):
                    cells = parsed_data["celulas"]

                if cells:
                    top_cell = cells[0]
                    c_name = top_cell.get("name", "Célula")
                    c_dist = top_cell.get("address", {}).get("distancia_km")
                    dist_str = f" a {c_dist:.2f} km de distância" if c_dist is not None else ""
                    achados = [
                        f"Encontrada a célula '{c_name}'{dist_str}.",
                        f"Total de {len(cells)} célula(s) encontrada(s) no raio pesquisado."
                    ]
                    rec = (
                        f"Informe ao usuário que a célula mais próxima encontrada foi a '{c_name}'"
                        f"{dist_str}. Apresente o endereço, dia/horário e líderes de forma acolhedora e convidativa."
                    )
                else:
                    msg = parsed_data.get("mensagem") if isinstance(parsed_data, dict) else "Nenhuma célula encontrada."
                    achados = [f"Nenhuma célula foi localizada para o endereço/CEP informado. ({msg})"]
                    rec = "Explique gentilmente que não foram encontradas células próximas nesse raio e solicite confirmação do endereço ou bairro/cidade."

                structured_payload = {
                    "achados": achados,
                    "dados": parsed_data,
                    "recomendacao": rec
                }
                return json.dumps(structured_payload, ensure_ascii=False)

            if "register_solicitation" in mcp_name.lower():
                structured_payload = {
                    "achados": [
                        "A solicitação/pedido de oração foi registrada com sucesso no sistema da igreja.",
                        f"Retorno do servidor: {parsed_data}"
                    ],
                    "dados": parsed_data,
                    "recomendacao": (
                        "Confirme calorosamente com o usuário que o seu pedido foi anotado com muito carinho "
                        "e que os responsáveis/pastores já receberam a informação para orar e prestar o apoio necessário."
                    )
                }
                return json.dumps(structured_payload, ensure_ascii=False)

            if "get_all_solicitation" in mcp_name.lower():
                solicitations = []
                if isinstance(parsed_data, list):
                    solicitations = parsed_data
                elif isinstance(parsed_data, dict):
                    solicitations = parsed_data.get("body") or parsed_data.get("solicitations") or []
                    if not isinstance(solicitations, list):
                        solicitations = [parsed_data]

                if solicitations:
                    achados = [
                        f"Foram encontradas {len(solicitations)} solicitação(ões) cadastrada(s).",
                    ]
                    rec = (
                        "Apresente ao usuário o status e o assunto dos seus pedidos de forma acolhedora, "
                        "usando lista simples (tópicos com traço), sem tabelas markdown."
                    )
                else:
                    achados = ["Nenhuma solicitação ou pedido foi encontrado para este usuário."]
                    rec = "Informe gentilmente que não foram encontrados pedidos registrados no momento e pergunte se gostaria de registrar um pedido de oração ou apoio."

                structured_payload = {
                    "achados": achados,
                    "dados": parsed_data,
                    "recomendacao": rec
                }
                return json.dumps(structured_payload, ensure_ascii=False)

            if "update_status_served" in mcp_name.lower():
                structured_payload = {
                    "achados": [
                        "A solicitação foi marcada como atendida/concluída com sucesso.",
                        f"Retorno do servidor: {parsed_data}"
                    ],
                    "dados": parsed_data,
                    "recomendacao": "Confirme que a solicitação foi marcada como atendida com sucesso."
                }
                return json.dumps(structured_payload, ensure_ascii=False)

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
