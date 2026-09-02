"""
Agent Graph Compiler & Execution Engine - Multi-Agent StateGraph with Parallelism & Reasoning Loops
"""
import logging
import time
import asyncio
import re
import json
from typing import List, Dict, Any, Optional, TypedDict, Callable
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.models.agent_graph import AgentGraph
from app.models.agent import Agent
from app.models.skill import Skill
from app.schemas.agent_graph import AgentGraphExecuteResponse, AgentGraphStepTrace
from app.utils.llm_fallback import FallbackChatOpenAI as ChatOpenAI
from app.config import settings

logger = logging.getLogger(__name__)


class AgentGraphState(TypedDict):
    """Execution state passed through the LangGraph StateGraph"""
    messages: List[Any]
    original_message: str
    context_data: Dict[str, Any]
    session_id: Optional[str]
    current_node_id: str
    step_history: List[Dict[str, Any]]
    parallel_outputs: Dict[str, Any]
    retry_counts: Dict[str, int]
    loop_feedbacks: Dict[str, str]
    final_output: str
    status: str
    error: Optional[str]


class AgentGraphCompiler:
    """
    Compiles an AgentGraph definition into an executable workflow,
    handling sequential execution, parallel fan-out/fan-in, conditional branches,
    iterative reasoning loops, and tool generation.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm_default = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.2,
            api_key=settings.OPENAI_API_KEY
        )

    async def execute_graph(
        self,
        graph: AgentGraph,
        message: str,
        context_data: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        history: Optional[List[Dict[str, Any]]] = None,
        override_definition: Optional[Dict[str, Any]] = None,
    ) -> AgentGraphExecuteResponse:
        """
        Executes the agent graph definition with the provided input message.
        Tracks all step transitions, latencies, and node outputs.
        """
        start_time = time.monotonic()
        definition = override_definition if override_definition is not None else (graph.definition or {})
        nodes = definition.get("nodes", [])
        edges = definition.get("edges", [])

        # Build initial messages including multi-turn history
        initial_messages: List[BaseMessage] = []
        for h in (history or []):
            r = h.get("role")
            c = h.get("content", "")
            if r == "user":
                initial_messages.append(HumanMessage(content=c))
            elif r == "assistant":
                initial_messages.append(AIMessage(content=c))
            elif r == "system":
                initial_messages.append(SystemMessage(content=c))
        initial_messages.append(HumanMessage(content=message))

        # Synchronize session_id and context_data bidirectionally
        safe_context = dict(context_data or {})
        if session_id and "session_id" not in safe_context:
            safe_context["session_id"] = str(session_id)
        if "session_id" in safe_context and not session_id:
            session_id = str(safe_context["session_id"])

        self._active_callbacks = []

        steps_trace: List[AgentGraphStepTrace] = []
        state: AgentGraphState = {
            "messages": initial_messages,
            "original_message": message,
            "context_data": safe_context,
            "session_id": session_id,
            "current_node_id": "",
            "step_history": [],
            "parallel_outputs": {},
            "retry_counts": {},
            "loop_feedbacks": {},
            "final_output": "",
            "status": "success",
            "error": None
        }

        if not nodes:
            return AgentGraphExecuteResponse(
                graph_id=graph.id,
                graph_name=graph.name,
                final_output="Grafo sem nós configurados.",
                steps=[],
                total_duration_ms=0.0,
                status="error",
                error="Nenhum nó encontrado no grafo.",
                session_id=session_id
            )

        # Index nodes and edges by id
        node_map: Dict[str, Dict[str, Any]] = {n["id"]: n for n in nodes if "id" in n}
        adj_list: Dict[str, List[Dict[str, Any]]] = {}
        for edge in edges:
            src = edge.get("source")
            if src:
                adj_list.setdefault(src, []).append(edge)

        # Find Start node (or first node)
        start_node = next((n for n in nodes if n.get("data", {}).get("type") in ("start", "trigger")), None)
        if not start_node:
            start_node = nodes[0]

        current_node_id = start_node["id"]
        iteration_count = 0
        max_iterations = graph.recursion_limit or 25

        while current_node_id and iteration_count < max_iterations:
            iteration_count += 1
            node = node_map.get(current_node_id)
            if not node:
                break

            node_type = node.get("data", {}).get("type", "agent")
            node_label = node.get("data", {}).get("label", node.get("label", current_node_id))
            node_config = node.get("data", {}).get("config", {})

            node_start = time.monotonic()
            step_trace = AgentGraphStepTrace(
                node_id=current_node_id,
                node_type=node_type,
                node_label=node_label,
                input_data={"message": state.get("original_message")}
            )

            try:
                # ── 1. START NODE ──────────────────────────────────────────────
                if node_type in ("start", "trigger"):
                    step_trace.output_data = "Grafo iniciado"
                    state["final_output"] = state["original_message"]

                # ── 2. AGENT NODE (System Agent or Inline Clean Agent) ───────────
                elif node_type == "agent":
                    agent_mode = node_config.get("agent_mode", "existing" if node_config.get("agent_id") else "inline")
                    inline_agent = node_config.get("inline_agent")

                    if agent_mode == "inline" or (inline_agent and not node_config.get("agent_id")):
                        # ── INLINE CLEAN AGENT ─────────────────────────────────
                        inline_cfg = inline_agent or node_config
                        inline_name = inline_cfg.get("name", "Agente Limpo")
                        system_prompt = inline_cfg.get("system_prompt") or "Você é um assistente prestativo e direto."
                        provider_id = inline_cfg.get("provider_id", "openai")
                        model_name = inline_cfg.get("model", "gpt-4o-mini")
                        temperature = float(inline_cfg.get("temperature", 0.7))
                        max_tokens = int(inline_cfg.get("max_tokens", 2000))
                        skill_ids = inline_cfg.get("skill_ids", []) or []
                        mcp_ids = inline_cfg.get("mcp_ids", []) or []

                        step_trace.agent_name = f"[Limpo] {inline_name}"

                        # 1. Inject Skills
                        skills_prompt = ""
                        if skill_ids:
                            clean_skill_ids = []
                            for sid in skill_ids:
                                try:
                                    clean_skill_ids.append(UUID(str(sid)))
                                except Exception:
                                    pass
                            if clean_skill_ids:
                                skill_res = await self.db.execute(
                                    select(Skill).where(Skill.id.in_(clean_skill_ids), Skill.is_active == True)
                                )
                                skills = skill_res.scalars().all()
                                for sk in skills:
                                    if sk.content_md:
                                        skills_prompt += f"\n\n---\n## 🔹 HABILIDADE / SKILL ATIVA: {sk.name}\n\n{sk.content_md}\n---\n"

                        # 2. Attach MCP Tools if configured
                        tools = []
                        if mcp_ids:
                            try:
                                from app.models.mcp import MCP
                                from app.services.mcp_tools import MCPToolExecutor
                                clean_mcp_ids = []
                                for mid in mcp_ids:
                                    try:
                                        clean_mcp_ids.append(UUID(str(mid)))
                                    except Exception:
                                        pass
                                if clean_mcp_ids:
                                    mcp_res = await self.db.execute(
                                        select(MCP).where(MCP.id.in_(clean_mcp_ids), MCP.is_active == True)
                                    )
                                    mcps = mcp_res.scalars().all()
                                    executor = MCPToolExecutor(self.db, state.get("context_data", {}) or {})
                                    for m in mcps:
                                        mcp_tools = await executor.create_langchain_tools(m)
                                        tools.extend(mcp_tools)
                            except Exception as e:
                                logger.warning(f"[AgentGraphCompiler] Erro ao carregar ferramentas MCP: {e}")

                        # 3. Build LLM via AgentFactory
                        from app.orchestrator.agent_factory import AgentFactory
                        from app.services.workflow_engine import resolve_template
                        factory = AgentFactory(self.db)
                        
                        provider_obj = None
                        if provider_id:
                            if str(provider_id).lower() in ("openai", "google", "deepseek", "openrouter"):
                                provider_obj = str(provider_id).lower()
                            else:
                                from app.models.ai_provider import AIProvider
                                try:
                                    prov_res = await self.db.execute(select(AIProvider).where(AIProvider.id == UUID(str(provider_id))))
                                    provider_obj = prov_res.scalar_one_or_none()
                                except Exception as prov_err:
                                    logger.warning(f"[AgentGraphCompiler] Could not load provider {provider_id}: {prov_err}")

                        context_mapping = node_config.get("context_mapping") or inline_cfg.get("context_mapping")
                        output_schema = node_config.get("output_schema") or inline_cfg.get("output_schema")
                        inject_full_context = node_config.get("inject_full_context", True)

                        eval_ctx = {
                            "$trigger": {"payload": state.get("context_data", {}) or {}},
                            "$request": state.get("context_data", {}) or {},
                            **(state.get("context_data", {}) or {}),
                            **{k: v for k, v in state.items() if k not in ("messages", "loop_feedbacks")}
                        }

                        # 1. Resolve Context Mapping (Payload Schema)
                        mapped_context_str = ""
                        if context_mapping and isinstance(context_mapping, dict):
                            resolved_mapping = {}
                            for k, v in context_mapping.items():
                                resolved_mapping[k] = resolve_template(v, eval_ctx)
                            mapped_context_str = (
                                f"\n\n## 📋 Dados Mapeados do Payload (Schema):\n"
                                f"```json\n{json.dumps(resolved_mapping, ensure_ascii=False, indent=2)}\n```\n"
                            )

                        # 2. Inject Full Context if requested
                        full_context_str = ""
                        if inject_full_context and state.get("context_data"):
                            safe_ctx = {k: v for k, v in state["context_data"].items() if not str(k).startswith("_")}
                            if safe_ctx:
                                full_context_str = (
                                    f"\n\n## 🌐 Contexto Global / Igreja:\n"
                                    f"<context_data>\n{json.dumps(safe_ctx, ensure_ascii=False, default=str)}\n</context_data>\n"
                                )

                        # 3. Output Schema Prompting
                        output_schema_str = ""
                        if output_schema:
                            schema_desc = json.dumps(output_schema, ensure_ascii=False, indent=2) if isinstance(output_schema, (dict, list)) else str(output_schema)
                            output_schema_str = (
                                f"\n\n## 📤 Esquema de Saída Obrigatório (JSON Output Schema):\n"
                                f"Você DEVE responder ESTRITAMENTE em formato JSON válido obedecendo ao seguinte schema:\n"
                                f"```json\n{schema_desc}\n```\n"
                            )

                        resolved_system_prompt = resolve_template(system_prompt, eval_ctx)
                        full_system_prompt = resolved_system_prompt + skills_prompt + mapped_context_str + full_context_str + output_schema_str

                        agent_cfg = {
                            "id": f"inline_{inline_name}",
                            "name": inline_name,
                            "model": model_name,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                            "provider": provider_obj or provider_id,
                            "output_schema": output_schema,
                            "config": inline_cfg.get("config", {}) or {},
                        }
                        llm = factory.create_llm(agent_cfg, session_id=session_id)

                        # 4. Prepare input messages with conversation history (STM / MTM)
                        load_stm = inline_cfg.get("load_stm", True)
                        load_mtm = inline_cfg.get("load_mtm", True)
                        mem_limit = int(inline_cfg.get("memory_limit", 6))
                        history_items = await self._load_stm_mtm_history(
                            session_id=session_id,
                            load_stm=load_stm,
                            load_mtm=load_mtm,
                            limit=mem_limit
                        )
                        history_msgs: List[BaseMessage] = []
                        for h in history_items:
                            if h.get("role") == "user":
                                history_msgs.append(HumanMessage(content=h.get("content", "")))
                            else:
                                history_msgs.append(AIMessage(content=h.get("content", "")))

                        input_msgs: List[BaseMessage] = [SystemMessage(content=full_system_prompt)]
                        input_msgs.extend(history_msgs)
                        for m in state["messages"]:
                            if isinstance(m, BaseMessage):
                                input_msgs.append(m)
                            elif isinstance(m, str):
                                input_msgs.append(HumanMessage(content=m))

                        # Inject loop feedback from Judge/Curator if available
                        feedback = state["loop_feedbacks"].get(current_node_id) or state["loop_feedbacks"].get("last")
                        if feedback:
                            input_msgs.append(SystemMessage(content=(
                                f"⚠️ FEEDBACK DO JUIZ / CURADOR (Sua resposta anterior precisa ser corrigida):\n"
                                f"{feedback}\n"
                                f"Por favor, revise os pontos apontados e gere uma resposta aprimorada."
                            )))
                            state["loop_feedbacks"].pop(current_node_id, None)
                            state["loop_feedbacks"].pop("last", None)

                        run_config = self._get_node_run_config(
                            node_label=node_label,
                            node_type=node_type,
                            graph_name=graph.name,
                            graph_id=graph.id,
                            node_id=current_node_id,
                            model_name=model_name,
                            state=state
                        )

                        # 5. Invoke LLM or ReAct Agent with tools
                        if tools:
                            from langgraph.prebuilt import create_react_agent
                            react_agent = create_react_agent(
                                model=llm,
                                tools=tools,
                                prompt=full_system_prompt,
                            )
                            react_input_msgs = list(history_msgs)
                            react_input_msgs.append(HumanMessage(content=state.get("original_message", "")))
                            result = await react_agent.ainvoke(
                                {'messages': react_input_msgs},
                                config=run_config
                            )
                            exec_messages = result.get('messages', [])
                            resp_content = ''
                            for msg in reversed(exec_messages):
                                if isinstance(msg, AIMessage) and msg.content:
                                    if not (hasattr(msg, 'tool_calls') and msg.tool_calls):
                                        resp_content = msg.content
                                        break
                            if not resp_content and exec_messages:
                                last_msg = exec_messages[-1]
                                resp_content = last_msg.content if hasattr(last_msg, 'content') else str(last_msg)
                        else:
                            resp = await llm.ainvoke(input_msgs, config=run_config)
                            resp_content = resp.content if isinstance(resp.content, str) else str(resp.content)

                        state["final_output"] = resp_content
                        state["messages"].append(AIMessage(content=resp_content))
                        step_trace.output_data = resp_content

                        # Persist response to STM/MTM if enabled
                        await self._persist_node_output(
                            session_id=session_id,
                            content=resp_content,
                            node_config=inline_cfg,
                            node_label=node_label,
                            context_data=state.get("context_data")
                        )

                    else:
                        # ── SYSTEM AGENT ───────────────────────────────────────
                        agent_id = node_config.get("agent_id")
                        agent_name = node_config.get("agent_name", "Agente")
                        step_trace.agent_id = str(agent_id) if agent_id else None
                        step_trace.agent_name = agent_name

                        context_mapping = node_config.get("context_mapping")
                        output_schema = node_config.get("output_schema")

                        eval_ctx = {
                            "$trigger": {"payload": state.get("context_data", {}) or {}},
                            "$request": state.get("context_data", {}) or {},
                            **(state.get("context_data", {}) or {}),
                            **{k: v for k, v in state.items() if k not in ("messages", "loop_feedbacks")}
                        }

                        if agent_id:
                            agent_obj = await self._get_agent_by_id(str(agent_id))
                            if agent_obj:
                                from app.orchestrator.agent_factory import AgentFactory
                                from app.services.workflow_engine import resolve_template
                                factory = AgentFactory(self.db)
                                agent_cfg = await factory.get_agent_config(agent_obj, context_data=state["context_data"])
                                if output_schema:
                                    agent_cfg["output_schema"] = output_schema

                                # Load STM / MTM history for System Agent
                                load_stm = node_config.get("load_stm", True)
                                load_mtm = node_config.get("load_mtm", True)
                                mem_limit = int(node_config.get("memory_limit", 6))
                                history_items = await self._load_stm_mtm_history(
                                    session_id=session_id,
                                    load_stm=load_stm,
                                    load_mtm=load_mtm,
                                    limit=mem_limit
                                )
                                history_msgs: List[BaseMessage] = []
                                for h in history_items:
                                    if h.get("role") == "user":
                                        history_msgs.append(HumanMessage(content=h.get("content", "")))
                                    else:
                                        history_msgs.append(AIMessage(content=h.get("content", "")))

                                input_msgs = history_msgs + list(state["messages"])

                                # Inject mapped context
                                if context_mapping and isinstance(context_mapping, dict):
                                    resolved_mapping = {}
                                    for k, v in context_mapping.items():
                                        resolved_mapping[k] = resolve_template(v, eval_ctx)
                                    input_msgs.insert(0, SystemMessage(content=(
                                        f"## 📋 Dados Mapeados do Payload (Schema):\n"
                                        f"```json\n{json.dumps(resolved_mapping, ensure_ascii=False, indent=2)}\n```"
                                    )))

                                if node_config.get("prompt_override"):
                                    resolved_override = resolve_template(node_config["prompt_override"], eval_ctx)
                                    input_msgs.append(SystemMessage(content=f"Instruções Adicionais do Grafo:\n{resolved_override}"))

                                feedback = state["loop_feedbacks"].get(current_node_id) or state["loop_feedbacks"].get("last")
                                if feedback:
                                    input_msgs.append(SystemMessage(content=(
                                        f"⚠️ FEEDBACK DO JUIZ / CURADOR (Sua resposta anterior precisa ser corrigida):\n"
                                        f"{feedback}\n"
                                        f"Por favor, revise os pontos apontados e gere uma resposta aprimorada."
                                    )))
                                    state["loop_feedbacks"].pop(current_node_id, None)
                                    state["loop_feedbacks"].pop("last", None)

                                # Execute agent (structured or standard)
                                if output_schema:
                                    structured_res = await factory.invoke_agent_structured(
                                        agent_config=agent_cfg,
                                        messages=input_msgs,
                                        context_data=state["context_data"]
                                    )
                                    if isinstance(structured_res, dict):
                                        resp_content = structured_res.get("output", json.dumps(structured_res, ensure_ascii=False))
                                    else:
                                        resp_content = str(structured_res)
                                else:
                                    resp_content = await factory.invoke_agent(
                                        agent_config=agent_cfg,
                                        messages=input_msgs,
                                        context_data=state["context_data"]
                                    )
                                state["final_output"] = resp_content
                                state["messages"].append(AIMessage(content=resp_content))
                                step_trace.output_data = resp_content

                                # Persist response to STM/MTM if enabled
                                await self._persist_node_output(
                                    session_id=session_id,
                                    content=resp_content,
                                    node_config=node_config,
                                    node_label=node_label,
                                    context_data=state.get("context_data")
                                )
                            else:
                                state["final_output"] = f"Agente '{agent_name}' não encontrado no banco."
                                step_trace.status = "error"
                                step_trace.error = "Agent not found"
                        else:
                            state["final_output"] = "Nenhum agente vinculado a este nó."
                            step_trace.output_data = state["final_output"]

                # ── 3. WORKFLOW / SUB-WORKFLOW NODE (Zero-Cost Data & Pipeline) ──
                elif node_type in ("workflow", "sub_workflow"):
                    wf_id = node_config.get("workflow_id")
                    wf_name = node_config.get("workflow_name", "Workflow")
                    output_key = node_config.get("output_key") or f"workflow_{current_node_id}"
                    inject_into_prompt = node_config.get("inject_into_prompt", True)

                    if wf_id:
                        try:
                            from app.services.workflow_engine import WorkflowEngine
                            engine = WorkflowEngine(self.db)

                            trigger_data = {
                                "message": state["original_message"],
                                "user_message": state["original_message"],
                                **state.get("context_data", {})
                            }

                            custom_inputs = node_config.get("input_mapping")
                            if custom_inputs and isinstance(custom_inputs, dict):
                                trigger_data.update(custom_inputs)

                            wf_uuid = UUID(str(wf_id))
                            exec_res = await engine.execute(
                                workflow_id=wf_uuid,
                                trigger_data=trigger_data,
                                session_id=state.get("session_id")
                            )

                            wf_output = exec_res.get("result") or exec_res.get("context") or {}
                            state["context_data"][output_key] = wf_output

                            if inject_into_prompt:
                                formatted_info = json.dumps(wf_output, ensure_ascii=False, indent=2) if isinstance(wf_output, (dict, list)) else str(wf_output)
                                state["messages"].append(SystemMessage(
                                    content=f"## Informações Coletadas via Workflow ({wf_name}):\n```json\n{formatted_info}\n```"
                                ))

                            step_trace.output_data = wf_output
                            if not state.get("final_output"):
                                state["final_output"] = str(wf_output)
                            logger.info(f"[AgentGraphCompiler] ⚙️ Workflow '{wf_name}' ({wf_id}) executado com sucesso no grafo.")
                        except Exception as wf_err:
                            logger.error(f"[AgentGraphCompiler] Erro ao executar workflow {wf_id}: {wf_err}", exc_info=True)
                            step_trace.status = "error"
                            step_trace.error = str(wf_err)
                            step_trace.output_data = f"Erro no Workflow: {str(wf_err)}"
                    else:
                        step_trace.output_data = "Nenhum workflow selecionado no bloco."

                # ── 4. ROUTER / SUPERVISOR NODE (Dynamic Semantic Routes) ───────
                elif node_type in ("router", "supervisor"):
                    outgoing_edges = adj_list.get(current_node_id, [])
                    routes = node_config.get("routes", [])

                    node_llm = await self._build_node_llm(node_config, default_temperature=0.2, default_max_tokens=1500, session_id=session_id)
                    mapped_ctx, full_ctx, eval_ctx = self._resolve_context_and_schema(node_config, state)
                    node_run_config = self._get_node_run_config(
                        node_label=node_label,
                        node_type=node_type,
                        graph_name=graph.name,
                        graph_id=graph.id,
                        node_id=current_node_id,
                        model_name=node_config.get("model", "default"),
                        state=state
                    )

                    # Load STM / MTM history for Router context
                    load_stm = node_config.get("load_stm", True)
                    load_mtm = node_config.get("load_mtm", True)
                    mem_limit = int(node_config.get("memory_limit", 4))
                    history_items = await self._load_stm_mtm_history(
                        session_id=session_id,
                        load_stm=load_stm,
                        load_mtm=load_mtm,
                        limit=mem_limit
                    )
                    history_str = self._format_history_for_prompt(history_items)

                    if routes:
                        route_descriptions = []
                        for idx, r in enumerate(routes):
                            r_id = r.get("id") or f"route_{idx}"
                            r_name = r.get("name") or f"Rota {idx + 1}"
                            r_desc = r.get("description") or "Sem descrição específica."
                            route_descriptions.append(f'- ID: "{r_id}" | Nome: "{r_name}" | Quando acionar: {r_desc}')

                        route_descriptions.append('- ID: "default" | Nome: "Outro / Fallback" | Quando acionar: Nenhuma das rotas acima corresponde adequadamente à intenção da mensagem.')

                        prompt_routes_str = "\n".join(route_descriptions)
                        supervisor_instruction = resolve_template(
                            node_config.get("prompt") or "Você é o Supervisor e Roteador Inteligente do Grafo de Agentes.",
                            eval_ctx
                        )

                        router_prompt = (
                            f"{supervisor_instruction}{history_str}{mapped_ctx}{full_ctx}\n\n"
                            "Analise cuidadosamente a mensagem do usuário (e o histórico de conversa acima, se houver) e escolha exatamente o ID da rota mais apropriada.\n\n"
                            f"ROTAS DISPONÍVEIS:\n{prompt_routes_str}\n\n"
                            "Responda SOMENTE em JSON com o formato estrito:\n"
                            "{\n"
                            '  "selected_route_id": "<ID da rota escolhida (ex: route_0, route_1 ou default)>",\n'
                            '  "reasoning": "<breve justificativa em 1 linha>"\n'
                            "}"
                        )

                        llm_resp = await node_llm.ainvoke([
                            SystemMessage(content=router_prompt),
                            HumanMessage(content=state["original_message"])
                        ], config=node_run_config)
                        content_str = llm_resp.content.strip()

                        chosen_route_id = None
                        reasoning = ""
                        try:
                            clean_json = re.search(r'\{.*\}', content_str, re.DOTALL)
                            if clean_json:
                                data = json.loads(clean_json.group(0))
                                chosen_route_id = data.get("selected_route_id")
                                reasoning = data.get("reasoning", "")
                        except Exception:
                            pass

                        if not chosen_route_id:
                            chosen_route_id = "default"

                        next_edge = next((e for e in outgoing_edges if e.get("sourceHandle") == chosen_route_id), None)
                        if not next_edge and chosen_route_id == "default":
                            next_edge = next((e for e in outgoing_edges if e.get("sourceHandle") in ("default", None) or "outro" in e.get("label", "").lower() or "fallback" in e.get("label", "").lower()), None)
                        if not next_edge and outgoing_edges:
                            next_edge = outgoing_edges[0]

                        chosen_id = next_edge.get("target") if next_edge else None
                        step_trace.output_data = f"Roteado para Rota '{chosen_route_id}' -> Nó destino: {chosen_id} (Motivo: {reasoning})"
                        
                        # Persist router output if explicitly configured (defaults to False for router)
                        if node_config.get("save_to_memory"):
                            await self._persist_node_output(
                                session_id=session_id,
                                content=f"Roteado para {chosen_route_id}: {reasoning}",
                                node_config=node_config,
                                node_label=node_label,
                                context_data=state.get("context_data")
                            )

                        state["current_node_id"] = chosen_id
                        step_trace.duration_ms = round((time.monotonic() - node_start) * 1000, 2)
                        steps_trace.append(step_trace)
                        current_node_id = chosen_id
                        continue

                    else:
                        choices = []
                        for e in outgoing_edges:
                            target_id = e.get("target")
                            target_node = node_map.get(target_id, {})
                            t_label = target_node.get("data", {}).get("label", target_id)
                            t_desc = target_node.get("data", {}).get("description", "")
                            choices.append(f"- ID '{target_id}': {t_label} ({t_desc})")

                        raw_prompt = node_config.get("prompt") or (
                            "Você é o Supervisor do Grafo de Agentes. Analise a mensagem do usuário e escolha exatamente o ID do nó de destino mais apropriado.\n"
                            f"Opções disponíveis:\n" + "\n".join(choices) + "\n\n"
                            "Responda SOMENTE em JSON com o formato: {\"selected_node_id\": \"<ID>\", \"reasoning\": \"<motivo>\"}"
                        )
                        custom_prompt = resolve_template(raw_prompt, eval_ctx) + history_str + mapped_ctx + full_ctx
                        
                        llm_resp = await node_llm.ainvoke([
                            SystemMessage(content=custom_prompt),
                            HumanMessage(content=state["original_message"])
                        ], config=node_run_config)
                        content_str = llm_resp.content.strip()
                        
                        chosen_id = None
                        try:
                            clean_json = re.search(r'\{.*\}', content_str, re.DOTALL)
                            if clean_json:
                                data = json.loads(clean_json.group(0))
                                chosen_id = data.get("selected_node_id")
                        except Exception:
                            pass
                        
                        if not chosen_id and outgoing_edges:
                            chosen_id = outgoing_edges[0].get("target")

                        step_trace.output_data = f"Roteado para {chosen_id} (resposta: {content_str[:150]}...)"
                        state["current_node_id"] = chosen_id
                        step_trace.duration_ms = round((time.monotonic() - node_start) * 1000, 2)
                        steps_trace.append(step_trace)
                        current_node_id = chosen_id
                        continue

                # ── 5. PARALLEL FAN-OUT NODE ────────────────────────────────────
                elif node_type == "parallel":
                    outgoing_edges = adj_list.get(current_node_id, [])
                    target_nodes = [node_map[e["target"]] for e in outgoing_edges if e.get("target") in node_map]
                    
                    parallel_tasks = []
                    for t_node in target_nodes:
                        parallel_tasks.append(self._execute_single_sub_node(t_node, state))
                    
                    results = await asyncio.gather(*parallel_tasks, return_exceptions=True)
                    parallel_dict = {}
                    for t_node, res in zip(target_nodes, results):
                        if isinstance(res, Exception):
                            parallel_dict[t_node["id"]] = f"Erro: {str(res)}"
                        else:
                            parallel_dict[t_node["id"]] = str(res)
                    
                    state["parallel_outputs"] = parallel_dict
                    step_trace.output_data = f"Executados {len(parallel_dict)} caminhos em paralelo: {list(parallel_dict.keys())}"

                # ── 6. SYNTHESIZER (FAN-IN) NODE ────────────────────────────────
                elif node_type == "synthesizer":
                    outputs = state.get("parallel_outputs", {})
                    combined_text = "\n\n".join([f"--- Parecer Especialista ({k}) ---\n{v}" for k, v in outputs.items()])
                    if not combined_text:
                        combined_text = state.get("final_output", "")

                    node_llm = await self._build_node_llm(node_config, default_temperature=0.6, default_max_tokens=2500, session_id=session_id)
                    mapped_ctx, full_ctx, eval_ctx = self._resolve_context_and_schema(node_config, state)
                    node_run_config = self._get_node_run_config(
                        node_label=node_label,
                        node_type=node_type,
                        graph_name=graph.name,
                        graph_id=graph.id,
                        node_id=current_node_id,
                        model_name=node_config.get("model", "default"),
                        state=state
                    )

                    # Load STM / MTM history for Synthesizer if configured
                    load_stm = node_config.get("load_stm", False)
                    load_mtm = node_config.get("load_mtm", False)
                    mem_limit = int(node_config.get("memory_limit", 6))
                    history_items = await self._load_stm_mtm_history(
                        session_id=session_id,
                        load_stm=load_stm,
                        load_mtm=load_mtm,
                        limit=mem_limit
                    )
                    history_str = self._format_history_for_prompt(history_items)

                    synth_prompt = resolve_template(node_config.get("prompt") or (
                        "Você é um Sintetizador Especialista. Sua função é consolidar as informações abaixo fornecidas por múltiplos agentes especialistas "
                        "em uma resposta única, coesa, natural e completa para o usuário final.\n\n"
                        f"Mensagem original do usuário: {state['original_message']}\n\n"
                        f"Contribuições dos especialistas:\n{combined_text}"
                    ), eval_ctx) + history_str + mapped_ctx + full_ctx

                    llm_resp = await node_llm.ainvoke([SystemMessage(content=synth_prompt)], config=node_run_config)
                    resp_text = llm_resp.content if isinstance(llm_resp.content, str) else str(llm_resp.content)
                    state["final_output"] = resp_text
                    state["messages"].append(AIMessage(content=resp_text))
                    step_trace.output_data = resp_text

                    # Persist synthesized output if save_to_memory is enabled (defaults to True)
                    await self._persist_node_output(
                        session_id=session_id,
                        content=resp_text,
                        node_config=node_config,
                        node_label=node_label,
                        context_data=state.get("context_data")
                    )

                # ── 7. CONDITION / DECISION NODE ───────────────────────────────
                elif node_type in ("condition", "decision"):
                    mode = node_config.get("mode", "llm")
                    condition_result = True
                    
                    if mode == "keyword":
                        keywords = node_config.get("keywords", [])
                        condition_result = any(k.lower() in state["final_output"].lower() for k in keywords)
                    elif mode == "regex":
                        pattern = node_config.get("regex", "")
                        condition_result = bool(re.search(pattern, state["final_output"])) if pattern else True
                    else:
                        node_llm = await self._build_node_llm(node_config, default_temperature=0.1, default_max_tokens=500, session_id=session_id)
                        mapped_ctx, full_ctx, eval_ctx = self._resolve_context_and_schema(node_config, state)
                        node_run_config = self._get_node_run_config(
                            node_label=node_label,
                            node_type=node_type,
                            graph_name=graph.name,
                            graph_id=graph.id,
                            node_id=current_node_id,
                            model_name=node_config.get("model", "default"),
                            state=state
                        )

                        criteria_str = resolve_template(node_config.get("criteria") or "A resposta atende à solicitação?", eval_ctx)
                        custom_instructions = resolve_template(node_config.get("prompt") or "", eval_ctx)
                        if custom_instructions:
                            custom_instructions = f"\nDiretrizes Adicionais:\n{custom_instructions}\n"

                        cond_prompt = (
                            "Você é um Avaliador Lógico de Condições. Analise o estado e a mensagem abaixo e responda estritamente com 'true' ou 'false'.\n\n"
                            f"Mensagem do Usuário: {state['original_message']}\n"
                            f"Última Resposta Gerada: {state['final_output']}\n"
                            f"Critério a ser avaliado: {criteria_str}\n"
                            f"{custom_instructions}"
                            f"{mapped_ctx}{full_ctx}\n\n"
                            "Responda EXCLUSIVAMENTE com a palavra 'true' ou 'false'."
                        )
                        llm_resp = await node_llm.ainvoke([SystemMessage(content=cond_prompt)], config=node_run_config)
                        condition_result = "true" in llm_resp.content.lower()

                    step_trace.output_data = f"Condição avaliada como: {condition_result}"

                    next_edge = next((
                        e for e in adj_list.get(current_node_id, [])
                        if (condition_result and (e.get("sourceHandle") in ("true", "sim", "yes", None) or "true" in e.get("label", "").lower() or "sim" in e.get("label", "").lower()))
                        or (not condition_result and (e.get("sourceHandle") in ("false", "nao", "não", "no") or "false" in e.get("label", "").lower() or "não" in e.get("label", "").lower()))
                    ), None)

                    if not next_edge and adj_list.get(current_node_id, []):
                        next_edge = adj_list[current_node_id][0]

                    chosen_id = next_edge.get("target") if next_edge else None
                    state["current_node_id"] = chosen_id
                    step_trace.duration_ms = round((time.monotonic() - node_start) * 1000, 2)
                    steps_trace.append(step_trace)
                    current_node_id = chosen_id
                    continue

                # ── 8. JUDGE / CURATOR / VERIFIER NODE (Feedback Loops) ─────────
                elif node_type in ("judge", "curator", "verifier"):
                    judge_criteria = node_config.get("criteria", "A resposta está completa, precisa, acolhedora e atende à solicitação?")
                    judge_mode = node_config.get("mode", "llm")
                    agent_judge_id = node_config.get("agent_id")
                    max_retries = node_config.get("max_retries", 2)
                    retries = state["retry_counts"].get(current_node_id, 0)

                    node_llm = await self._build_node_llm(node_config, default_temperature=0.1, default_max_tokens=1000, session_id=session_id)
                    mapped_ctx, full_ctx, eval_ctx = self._resolve_context_and_schema(node_config, state)
                    judge_criteria = resolve_template(judge_criteria, eval_ctx)
                    judge_instruction_custom = resolve_template(
                        node_config.get("prompt") or "Você é o Juiz e Curador de Qualidade do Atendimento.",
                        eval_ctx
                    )

                    # Load STM / MTM history for Judge if configured
                    load_stm = node_config.get("load_stm", False)
                    load_mtm = node_config.get("load_mtm", False)
                    mem_limit = int(node_config.get("memory_limit", 4))
                    history_items = await self._load_stm_mtm_history(
                        session_id=session_id,
                        load_stm=load_stm,
                        load_mtm=load_mtm,
                        limit=mem_limit
                    )
                    history_str = self._format_history_for_prompt(history_items)

                    is_approved = True
                    feedback = ""
                    score = 10

                    if judge_mode == "agent" and agent_judge_id:
                        try:
                            agent_obj = await self._get_agent_by_id(str(agent_judge_id))
                            if agent_obj:
                                from app.orchestrator.agent_factory import AgentFactory
                                factory = AgentFactory(self.db)
                                judge_cfg = await factory.get_agent_config(agent_obj, context_data=state["context_data"])
                                
                                judge_instruction = (
                                    f"Você é o Juiz e Curador de Qualidade ({agent_obj.name}).\n"
                                    f"Critérios de Avaliação: {judge_criteria}\n\n"
                                    f"Pergunta do Usuário: {state['original_message']}\n"
                                    f"Resposta Gerada: {state['final_output']}\n"
                                    f"{history_str}{mapped_ctx}{full_ctx}\n\n"
                                    "Avalie a resposta e responda EXCLUSIVAMENTE em formato JSON:\n"
                                    "{\n"
                                    '  "status": "APPROVED" ou "REJECTED",\n'
                                    '  "score": <nota de 1 a 10>,\n'
                                    '  "feedback": "<instruções específicas do que o agente deve corrigir/melhorar se rejeitado, ou breve motivo da aprovação>"\n'
                                    "}"
                                )
                                judge_msgs = [SystemMessage(content=judge_instruction)]
                                raw_resp = await factory.invoke_agent(
                                    agent_config=judge_cfg,
                                    messages=judge_msgs,
                                    context_data=state["context_data"]
                                )
                                clean_json = re.search(r'\{.*\}', raw_resp, re.DOTALL)
                                if clean_json:
                                    data = json.loads(clean_json.group(0))
                                    is_approved = data.get("status", "").upper() == "APPROVED"
                                    feedback = data.get("feedback", "")
                                    score = data.get("score", 10 if is_approved else 5)
                                else:
                                    is_approved = "approved" in raw_resp.lower() or "aprovado" in raw_resp.lower()
                                    feedback = raw_resp
                        except Exception as j_err:
                            logger.warning(f"[AgentGraphCompiler] Erro ao executar agente juiz: {j_err}")
                            is_approved = True
                    else:
                        v_prompt = (
                            f"{judge_instruction_custom}\n\n"
                            f"Mensagem do Usuário: {state['original_message']}\n"
                            f"Resposta Gerada pelo Agente: {state['final_output']}\n\n"
                            f"Critérios de Curadoria / Qualidade:\n{judge_criteria}\n\n"
                            f"{history_str}{mapped_ctx}{full_ctx}\n\n"
                            "Avalie se a resposta cumpre os critérios e está aprovada para entrega final.\n"
                            "Responda SOMENTE em JSON no seguinte formato estrito:\n"
                            "{\n"
                            '  "status": "APPROVED" ou "REJECTED",\n'
                            '  "score": <nota de 1 a 10>,\n'
                            '  "feedback": "<instruções cirúrgicas e específicas do que o agente deve corrigir caso rejeitado, ou breve resumo de aprovação>"\n'
                            "}"
                        )
                        node_run_config = self._get_node_run_config(
                            node_label=node_label,
                            node_type=node_type,
                            graph_name=graph.name,
                            graph_id=graph.id,
                            node_id=current_node_id,
                            model_name=node_config.get("model", "default"),
                            state=state
                        )
                        llm_resp = await node_llm.ainvoke([SystemMessage(content=v_prompt)], config=node_run_config)
                        try:
                            clean_json = re.search(r'\{.*\}', llm_resp.content, re.DOTALL)
                            if clean_json:
                                data = json.loads(clean_json.group(0))
                                is_approved = data.get("status", "").upper() == "APPROVED"
                                feedback = data.get("feedback", "")
                                score = data.get("score", 10 if is_approved else 5)
                        except Exception:
                            is_approved = "approved" in llm_resp.content.lower() or "aprovado" in llm_resp.content.lower()

                    step_trace.feedback = feedback

                    if is_approved or retries >= max_retries:
                        if retries >= max_retries and not is_approved:
                            step_trace.output_data = f"⚠️ Limite de Loops ({retries}/{max_retries}) atingido -> Aprovado com ressalvas: {feedback}"
                        else:
                            step_trace.output_data = f"✅ Aprovado (Nota {score}/10) | {feedback or 'Resposta conforme os padrões esperados.'}"
                        
                        next_edge = next((
                            e for e in adj_list.get(current_node_id, [])
                            if e.get("sourceHandle") in ("approved", "true", "success", "sucesso") 
                            or "aprov" in e.get("label", "").lower() 
                            or "true" in e.get("label", "").lower()
                            or "sim" in e.get("label", "").lower()
                        ), None)
                    else:
                        state["retry_counts"][current_node_id] = retries + 1
                        state["loop_feedbacks"][current_node_id] = feedback
                        state["loop_feedbacks"]["last"] = feedback
                        step_trace.output_data = f"❌ Reprovado (Nota {score}/10) -> Loop de Correção ({retries + 1}/{max_retries}): {feedback}"
                        
                        next_edge = next((
                            e for e in adj_list.get(current_node_id, [])
                            if e.get("sourceHandle") in ("retry", "false", "loop_in_left", "loop_in_right", "loop", "rejected", "reprovado")
                            or "reprov" in e.get("label", "").lower()
                            or "loop" in e.get("label", "").lower()
                            or "refazer" in e.get("label", "").lower()
                            or "false" in e.get("label", "").lower()
                            or "nao" in e.get("label", "").lower()
                            or "não" in e.get("label", "").lower()
                        ), None)

                    if not next_edge and adj_list.get(current_node_id):
                        next_edge = adj_list[current_node_id][0]

                    chosen_id = next_edge.get("target") if next_edge else None
                    step_trace.duration_ms = round((time.monotonic() - node_start) * 1000, 2)
                    steps_trace.append(step_trace)
                    current_node_id = chosen_id
                    continue

                # ── 9. TOOL / ACTION NODE ──────────────────────────────────────
                elif node_type in ("tool", "action"):
                    action_type = node_config.get("action_type", "mcp")
                    step_trace.output_data = f"Ação executada: {action_type}"

                # ── 10. END NODE ───────────────────────────────────────────────
                elif node_type in ("end", "output"):
                    step_trace.output_data = "Grafo finalizado com sucesso"
                    step_trace.duration_ms = round((time.monotonic() - node_start) * 1000, 2)
                    steps_trace.append(step_trace)
                    break

            except Exception as e:
                logger.error(f"[AgentGraphCompiler] Erro ao executar nó '{node_label}' ({current_node_id}): {e}", exc_info=True)
                step_trace.status = "error"
                step_trace.error = str(e)
                step_trace.output_data = f"❌ Erro no nó '{node_label}': {str(e)}"
                state["status"] = "error"
                state["error"] = str(e)
                if not state.get("final_output"):
                    state["final_output"] = f"❌ Erro no nó '{node_label}': {str(e)}"

            step_trace.duration_ms = round((time.monotonic() - node_start) * 1000, 2)
            steps_trace.append(step_trace)

            # Move to next default outgoing edge
            outgoing = adj_list.get(current_node_id, [])
            current_node_id = outgoing[0].get("target") if outgoing else None

        total_duration = round((time.monotonic() - start_time) * 1000, 2)
        response = AgentGraphExecuteResponse(
            graph_id=graph.id,
            graph_name=graph.name,
            final_output=state.get("final_output") or state.get("original_message", ""),
            steps=steps_trace,
            total_duration_ms=total_duration,
            status=state.get("status", "success"),
            error=state.get("error"),
            context_data=state.get("context_data"),
            session_id=session_id
        )

        # Flush Langfuse traces so they appear immediately on dashboard
        self._flush_langfuse_traces()

        return response

    def _flush_langfuse_traces(self):
        """Flushes all Langfuse callbacks and global client to ensure all spans reach the dashboard"""
        if hasattr(self, "_active_callbacks") and self._active_callbacks:
            for cb in self._active_callbacks:
                try:
                    if hasattr(cb, "flush"):
                        cb.flush()
                    elif hasattr(cb, "client") and hasattr(cb.client, "flush"):
                        cb.client.flush()
                except Exception as flush_err:
                    logger.debug(f"[AgentGraphCompiler] Langfuse callback flush: {flush_err}")
            self._active_callbacks.clear()

        try:
            from langfuse import Langfuse
            Langfuse().flush()
        except Exception:
            pass

    async def _execute_single_sub_node(self, node: Dict[str, Any], state: AgentGraphState) -> str:
        """Helper to execute an isolated node in parallel (supports system & inline agents)"""
        node_type = node.get("data", {}).get("type", "agent")
        node_config = node.get("data", {}).get("config", {})
        
        if node_type == "agent":
            agent_mode = node_config.get("agent_mode", "existing" if node_config.get("agent_id") else "inline")
            inline_agent = node_config.get("inline_agent")

            if agent_mode == "inline" or (inline_agent and not node_config.get("agent_id")):
                inline_cfg = inline_agent or node_config
                system_prompt = inline_cfg.get("system_prompt") or "Você é um assistente especialista."
                provider_id = inline_cfg.get("provider_id", "openai")
                model_name = inline_cfg.get("model", "gpt-4o-mini")
                temperature = float(inline_cfg.get("temperature", 0.7))
                max_tokens = int(inline_cfg.get("max_tokens", 2000))

                from app.orchestrator.agent_factory import AgentFactory
                factory = AgentFactory(self.db)
                agent_cfg = {
                    "id": f"inline_sub_{node.get('id')}",
                    "name": inline_cfg.get("name", "Agente Limpo"),
                    "model": model_name,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "provider": provider_id,
                    "config": inline_cfg.get("config", {}) or {},
                }
                llm = factory.create_llm(agent_cfg, session_id=state.get("session_id"))
                msgs = [SystemMessage(content=system_prompt), HumanMessage(content=state["original_message"])]
                sub_run_config = self._get_node_run_config(
                    node_label=node.get("data", {}).get("label", "Sub-nó"),
                    node_type=node_type,
                    graph_name="Parallel Branch",
                    graph_id="parallel",
                    node_id=node.get("id"),
                    model_name=model_name,
                    state=state
                )
                resp = await llm.ainvoke(msgs, config=sub_run_config)
                return resp.content if isinstance(resp.content, str) else str(resp.content)

            else:
                agent_id = node_config.get("agent_id")
                if agent_id:
                    agent_obj = await self._get_agent_by_id(str(agent_id))
                    if agent_obj:
                        from app.orchestrator.agent_factory import AgentFactory
                        factory = AgentFactory(self.db)
                        agent_cfg = await factory.get_agent_config(agent_obj, context_data=state["context_data"])
                        return await factory.invoke_agent(
                            agent_config=agent_cfg,
                            messages=state["messages"],
                            context_data=state["context_data"]
                        )
        return f"Sub-nó {node.get('id')} executado"

    async def _build_node_llm(
        self,
        node_config: Dict[str, Any],
        default_temperature: float = 0.5,
        default_max_tokens: int = 2000,
        session_id: Optional[str] = None
    ):
        """
        Builds an LLM dynamically for ANY agentic node (router, judge, synthesizer, condition, etc.)
        using the node's configured provider, model, temperature, and max_tokens.
        Falls back to self.llm_default if no custom model is configured.
        """
        provider_id = node_config.get("provider_id")
        model_name = node_config.get("model")

        if not provider_id and not model_name:
            return self.llm_default

        from app.orchestrator.agent_factory import AgentFactory
        factory = AgentFactory(self.db)

        provider_obj = None
        if provider_id:
            if str(provider_id).lower() in ("openai", "google", "deepseek", "openrouter"):
                provider_obj = str(provider_id).lower()
            else:
                from app.models.ai_provider import AIProvider
                try:
                    prov_res = await self.db.execute(select(AIProvider).where(AIProvider.id == UUID(str(provider_id))))
                    provider_obj = prov_res.scalar_one_or_none()
                except Exception:
                    provider_obj = provider_id

        agent_cfg = {
            "id": f"node_llm_{node_config.get('id', 'custom')}",
            "name": node_config.get("name", "NodeLLM"),
            "model": model_name or "gpt-4o-mini",
            "temperature": float(node_config.get("temperature", default_temperature)),
            "max_tokens": int(node_config.get("max_tokens", default_max_tokens)),
            "provider": provider_obj or provider_id or "openai",
            "config": node_config.get("config", {}) or {},
        }
        if node_config.get("output_schema"):
            agent_cfg["output_schema"] = node_config["output_schema"]

        return factory.create_llm(agent_cfg, session_id=session_id)

    def _resolve_context_and_schema(
        self,
        node_config: Dict[str, Any],
        state: AgentGraphState
    ) -> tuple[str, str, Dict[str, Any]]:
        """
        Resolves context mapping, full context injection, and returns (mapped_context_str, full_context_str, eval_ctx)
        """
        from app.services.workflow_engine import resolve_template

        context_mapping = node_config.get("context_mapping")
        inject_full_context = node_config.get("inject_full_context", True)

        eval_ctx = {
            "$trigger": {"payload": state.get("context_data", {}) or {}},
            "$request": state.get("context_data", {}) or {},
            **(state.get("context_data", {}) or {}),
            **{k: v for k, v in state.items() if k not in ("messages", "loop_feedbacks")}
        }

        mapped_context_str = ""
        if context_mapping and isinstance(context_mapping, dict):
            resolved_mapping = {}
            for k, v in context_mapping.items():
                resolved_mapping[k] = resolve_template(v, eval_ctx)
            mapped_context_str = (
                f"\n\n## 📋 Dados Mapeados do Payload (Schema):\n"
                f"```json\n{json.dumps(resolved_mapping, ensure_ascii=False, indent=2)}\n```\n"
            )

        full_context_str = ""
        if inject_full_context and state.get("context_data"):
            safe_ctx = {k: v for k, v in state["context_data"].items() if not str(k).startswith("_")}
            if safe_ctx:
                full_context_str = (
                    f"\n\n## 🌐 Contexto Global / Igreja:\n"
                    f"<context_data>\n{json.dumps(safe_ctx, ensure_ascii=False, default=str)}\n</context_data>\n"
                )

        return mapped_context_str, full_context_str, eval_ctx

    def _get_node_run_config(
        self,
        node_label: str,
        node_type: str,
        graph_name: str,
        graph_id: Any,
        node_id: str,
        model_name: Optional[str] = None,
        state: Optional[AgentGraphState] = None
    ) -> Any:
        """Creates a RunnableConfig with Langfuse and LangSmith tracing for any graph node execution"""
        from app.config import get_langfuse_callback
        from langchain_core.runnables import RunnableConfig

        ctx = (state.get("context_data", {}) if state else {}) or {}
        user_phone = ctx.get("member", {}).get("phone") or ctx.get("user_phone") or ctx.get("phone")
        sess_id = (state.get("session_id") if state else None) or ctx.get("session_id")
        instancia_id = ctx.get("global", {}).get("instancia")
        church_id = ctx.get("church", {}).get("_id") or ctx.get("church", {}).get("id")

        callbacks = []
        try:
            langfuse_cb = get_langfuse_callback()
            if langfuse_cb:
                callbacks.append(langfuse_cb)
                if not hasattr(self, "_active_callbacks") or self._active_callbacks is None:
                    self._active_callbacks = []
                self._active_callbacks.append(langfuse_cb)
        except Exception as lf_err:
            logger.debug(f"[AgentGraphCompiler] Langfuse callback error: {lf_err}")

        tags = [
            "agent_graph",
            f"graph:{graph_name}",
            f"node_type:{node_type}",
            f"node:{node_label}"
        ]
        if instancia_id:
            tags.append(f"instancia:{instancia_id}")
        if church_id:
            tags.append(f"church:{church_id}")

        metadata = {
            "graph_id": str(graph_id),
            "graph_name": graph_name,
            "node_id": str(node_id),
            "node_type": node_type,
            "node_label": node_label,
            "model": model_name or "default",
        }
        if user_phone:
            metadata["langfuse_user_id"] = str(user_phone)
        if sess_id:
            metadata["langfuse_session_id"] = str(sess_id)
        if church_id:
            metadata["church_id"] = str(church_id)
        if tags:
            metadata["langfuse_tags"] = tags

        return RunnableConfig(
            run_name=f"Graph [{graph_name}] -> {node_label} ({node_type})",
            metadata=metadata,
            tags=tags,
            callbacks=callbacks if callbacks else None,
        )

    async def _load_stm_mtm_history(
        self,
        session_id: Optional[str],
        load_stm: bool = True,
        load_mtm: bool = True,
        limit: int = 6
    ) -> List[Dict[str, Any]]:
        """
        Loads recent conversation history from Redis (STM) and/or PostgreSQL (MTM).
        Returns a list of dicts: [{"role": "user"|"assistant", "content": "..."}] in chronological order.
        """
        if not session_id or (not load_stm and not load_mtm):
            return []

        history: List[Dict[str, Any]] = []

        # 1. Read from Redis (STM - Short Term Memory)
        if load_stm:
            try:
                from app.redis_client import redis_client
                stm_raw = await redis_client.get_conversation(str(session_id), limit=limit)
                if stm_raw:
                    for item in stm_raw:
                        if isinstance(item, dict) and item.get("content"):
                            history.append({
                                "role": item.get("role", "user"),
                                "content": item.get("content", ""),
                                "source": "STM"
                            })
            except Exception as stm_err:
                logger.warning(f"[AgentGraphCompiler] Erro ao carregar STM de {session_id}: {stm_err}")

        # 2. Read from PostgreSQL (MTM - Medium Term Memory) if requested
        if load_mtm:
            try:
                from app.models.conversation_message import ConversationMessage
                stmt = (
                    select(ConversationMessage)
                    .where(ConversationMessage.session_id == str(session_id))
                    .order_by(ConversationMessage.created_at.desc())
                    .limit(limit)
                )
                res = await self.db.execute(stmt)
                rows = res.scalars().all()
                mtm_msgs = []
                for r in reversed(rows):
                    mtm_msgs.append({
                        "role": "assistant" if r.role in ("assistant", "fromMe", "supportResponse") else "user",
                        "content": r.content,
                        "source": "MTM"
                    })
                
                if not history:
                    history = mtm_msgs
                else:
                    existing_contents = {m["content"] for m in history}
                    for m in mtm_msgs:
                        if m["content"] not in existing_contents:
                            history.insert(0, m)
                            existing_contents.add(m["content"])
            except Exception as mtm_err:
                logger.warning(f"[AgentGraphCompiler] Erro ao carregar MTM de {session_id}: {mtm_err}")

        return history[-limit:] if limit > 0 else history

    def _format_history_for_prompt(self, history: List[Dict[str, Any]]) -> str:
        """Formats conversation history items as a markdown block for system/router prompts"""
        if not history:
            return ""
        lines = []
        for h in history:
            role_label = "Membro" if h.get("role") == "user" else "Igreja / Assistente"
            lines.append(f"- [{role_label}]: {h.get('content', '')}")
        return (
            f"\n\n## 📜 Histórico Recente da Conversa (STM / MTM):\n"
            f"Use o histórico abaixo para entender referências a mensagens anteriores, respostas a perguntas feitas pela igreja ou continuidade do assunto:\n"
            + "\n".join(lines) + "\n"
        )

    async def _persist_node_output(
        self,
        session_id: Optional[str],
        content: str,
        node_config: Dict[str, Any],
        node_label: str,
        context_data: Optional[Dict[str, Any]] = None
    ):
        """
        Persists the assistant response to Redis (STM) and PostgreSQL (MTM)
        when save_to_memory is enabled for this node.
        """
        if not session_id or not content or not node_config.get("save_to_memory", True):
            return

        # 1. Save to Redis (STM)
        try:
            from app.redis_client import redis_client
            ttl_seconds = int(node_config.get("stm_ttl_seconds", 86400))
            await redis_client.add_message(
                session_id=str(session_id),
                role="assistant",
                content=content,
                ttl_seconds=ttl_seconds
            )
            logger.info(f"[AgentGraphCompiler] 💾 Saída de '{node_label}' salva no STM (Redis) para sessão {session_id}")
        except Exception as redis_err:
            logger.warning(f"[AgentGraphCompiler] Erro ao salvar STM em Redis: {redis_err}")

        # 2. Save to PostgreSQL (MTM)
        try:
            from app.models.conversation_message import ConversationMessage
            from app.models.agent import Agent
            import uuid

            target_agent_id = None
            if node_config.get("agent_id"):
                try:
                    target_agent_id = uuid.UUID(str(node_config["agent_id"]))
                except Exception:
                    pass

            if not target_agent_id and context_data and context_data.get("agent_id"):
                try:
                    target_agent_id = uuid.UUID(str(context_data["agent_id"]))
                except Exception:
                    pass

            if not target_agent_id:
                agent_res = await self.db.execute(select(Agent.id).limit(1))
                target_agent_id = agent_res.scalar_one_or_none()

            if target_agent_id:
                msg = ConversationMessage(
                    id=uuid.uuid4(),
                    agent_id=target_agent_id,
                    session_id=str(session_id),
                    role="assistant",
                    content=content,
                    webhook_path=f"agent_graph/{node_label}"
                )
                self.db.add(msg)
                await self.db.commit()
                logger.info(f"[AgentGraphCompiler] 💾 Saída de '{node_label}' salva no MTM (Postgres) para sessão {session_id}")
        except Exception as mtm_err:
            logger.warning(f"[AgentGraphCompiler] Erro ao salvar MTM em Postgres: {mtm_err}")

    async def _get_agent_by_id(self, agent_id: str) -> Optional[Agent]:
        """Fetch agent model by ID with relationships"""
        try:
            uid = UUID(agent_id)
            result = await self.db.execute(
                select(Agent)
                .options(
                    selectinload(Agent.mcps),
                    selectinload(Agent.skills),
                    selectinload(Agent.information_bases),
                    selectinload(Agent.vfs_knowledge_bases),
                    selectinload(Agent.collaborator_settings),
                    selectinload(Agent.provider)
                )
                .where(Agent.id == uid)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"[AgentGraphCompiler] Erro ao buscar agente {agent_id}: {e}")
            return None


def build_graph_tool(
    graph: AgentGraph,
    db: AsyncSession,
    context_data: Optional[Dict[str, Any]] = None,
    tool_name_override: Optional[str] = None,
    tool_desc_override: Optional[str] = None
) -> StructuredTool:
    """
    Wraps an AgentGraph into a callable LangChain StructuredTool.
    Allows any standard agent to call this entire graph as a sub-routine/tool.
    """
    safe_name = tool_name_override or f"grafo_{re.sub(r'[^a-zA-Z0-9_]', '_', graph.name.lower())[:30]}"
    description = tool_desc_override or graph.description or f"Executa o fluxo de orquestração do grafo '{graph.name}'"

    class GraphToolInput(BaseModel):
        query: str = Field(..., description="A mensagem, pergunta ou instrução a ser processada pelo grafo de agentes")
        extra_context: Optional[Dict[str, Any]] = Field(default=None, description="Contexto adicional em formato chave-valor")

    async def _run_graph(query: str, extra_context: Optional[Dict[str, Any]] = None) -> str:
        ctx = dict(context_data or {})
        if extra_context:
            ctx.update(extra_context)
        compiler = AgentGraphCompiler(db)
        res = await compiler.execute_graph(graph=graph, message=query, context_data=ctx)
        return res.final_output

    return StructuredTool.from_function(
        coroutine=_run_graph,
        name=safe_name,
        description=description,
        args_schema=GraphToolInput
    )
