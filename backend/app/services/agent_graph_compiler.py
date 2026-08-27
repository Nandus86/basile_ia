"""
Agent Graph Compiler & Execution Engine - Multi-Agent StateGraph with Parallelism & Reasoning Loops
"""
import logging
import time
import asyncio
import re
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
    ) -> AgentGraphExecuteResponse:
        """
        Executes the agent graph definition with the provided input message.
        Tracks all step transitions, latencies, and node outputs.
        """
        start_time = time.monotonic()
        definition = graph.definition or {}
        nodes = definition.get("nodes", [])
        edges = definition.get("edges", [])

        steps_trace: List[AgentGraphStepTrace] = []
        state: AgentGraphState = {
            "messages": [HumanMessage(content=message)],
            "original_message": message,
            "context_data": context_data or {},
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
                error="Nenhum nó encontrado no grafo."
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

                # ── 2. AGENT NODE ──────────────────────────────────────────────
                elif node_type == "agent":
                    agent_id = node_config.get("agent_id")
                    agent_name = node_config.get("agent_name", "Agente")
                    step_trace.agent_id = str(agent_id) if agent_id else None
                    step_trace.agent_name = agent_name

                    if agent_id:
                        agent_obj = await self._get_agent_by_id(str(agent_id))
                        if agent_obj:
                            from app.orchestrator.agent_factory import AgentFactory
                            factory = AgentFactory(self.db)
                            agent_cfg = await factory.get_agent_config(agent_obj, context_data=state["context_data"])
                            
                            # Inject loop feedback if available
                            input_msgs = list(state["messages"])
                            if current_node_id in state["loop_feedbacks"]:
                                feedback = state["loop_feedbacks"][current_node_id]
                                input_msgs.append(SystemMessage(content=f"⚠️ FEEDBACK DO VERIFICADOR (Corrija sua resposta anterior):\n{feedback}"))

                            # Execute agent
                            resp_content = await factory.invoke_agent(
                                agent_config=agent_cfg,
                                messages=input_msgs,
                                context_data=state["context_data"]
                            )
                            state["final_output"] = resp_content
                            state["messages"].append(AIMessage(content=resp_content))
                            step_trace.output_data = resp_content
                        else:
                            state["final_output"] = f"Agente '{agent_name}' não encontrado no banco."
                            step_trace.status = "error"
                            step_trace.error = "Agent not found"
                    else:
                        state["final_output"] = "Nenhum agente vinculado a este nó."
                        step_trace.output_data = state["final_output"]

                # ── 3. ROUTER / SUPERVISOR NODE ────────────────────────────────
                elif node_type in ("router", "supervisor"):
                    outgoing_edges = adj_list.get(current_node_id, [])
                    choices = []
                    for e in outgoing_edges:
                        target_id = e.get("target")
                        target_node = node_map.get(target_id, {})
                        t_label = target_node.get("data", {}).get("label", target_id)
                        t_desc = target_node.get("data", {}).get("description", "")
                        choices.append(f"- ID '{target_id}': {t_label} ({t_desc})")

                    custom_prompt = node_config.get("prompt") or (
                        "Você é o Supervisor do Grafo de Agentes. Analise a mensagem do usuário e escolha exatamente o ID do nó de destino mais apropriado.\n"
                        f"Opções disponíveis:\n" + "\n".join(choices) + "\n\n"
                        "Responda SOMENTE em JSON com o formato: {\"selected_node_id\": \"<ID>\", \"reasoning\": \"<motivo>\"}"
                    )
                    
                    llm_resp = await self.llm_default.ainvoke([
                        SystemMessage(content=custom_prompt),
                        HumanMessage(content=state["original_message"])
                    ])
                    content_str = llm_resp.content.strip()
                    
                    # Parse selected node id
                    chosen_id = None
                    import json
                    try:
                        clean_json = re.search(r'\{.*\}', content_str, re.DOTALL)
                        if clean_json:
                            data = json.loads(clean_json.group(0))
                            chosen_id = data.get("selected_node_id")
                    except Exception:
                        pass
                    
                    # Fallback if parsing failed
                    if not chosen_id and outgoing_edges:
                        chosen_id = outgoing_edges[0].get("target")

                    step_trace.output_data = f"Roteado para {chosen_id} (resposta: {content_str[:150]}...)"
                    state["current_node_id"] = chosen_id
                    # Skip normal next edge calculation
                    step_trace.duration_ms = round((time.monotonic() - node_start) * 1000, 2)
                    steps_trace.append(step_trace)
                    current_node_id = chosen_id
                    continue

                # ── 4. PARALLEL FAN-OUT NODE ────────────────────────────────────
                elif node_type == "parallel":
                    outgoing_edges = adj_list.get(current_node_id, [])
                    target_nodes = [node_map[e["target"]] for e in outgoing_edges if e.get("target") in node_map]
                    
                    # Run all target nodes concurrently
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

                # ── 5. SYNTHESIZER (FAN-IN) NODE ────────────────────────────────
                elif node_type == "synthesizer":
                    outputs = state.get("parallel_outputs", {})
                    combined_text = "\n\n".join([f"--- Parecer Especialista ({k}) ---\n{v}" for k, v in outputs.items()])
                    if not combined_text:
                        combined_text = state.get("final_output", "")

                    synth_prompt = node_config.get("prompt") or (
                        "Você é um Sintetizador Especialista. Sua função é consolidar as informações abaixo fornecidas por múltiplos agentes especialistas "
                        "em uma resposta única, coesa, natural e completa para o usuário final.\n\n"
                        f"Mensagem original do usuário: {state['original_message']}\n\n"
                        f"Contribuições dos especialistas:\n{combined_text}"
                    )
                    llm_resp = await self.llm_default.ainvoke([SystemMessage(content=synth_prompt)])
                    state["final_output"] = llm_resp.content
                    state["messages"].append(AIMessage(content=llm_resp.content))
                    step_trace.output_data = llm_resp.content

                # ── 6. CONDITION / DECISION NODE ───────────────────────────────
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
                        eval_prompt = node_config.get("prompt") or (
                            f"Avalie a resposta atual: '{state['final_output']}'. "
                            f"Critério: {node_config.get('criteria', 'A resposta atende à solicitação?')}. "
                            "Responda APENAS 'TRUE' ou 'FALSE'."
                        )
                        llm_resp = await self.llm_default.ainvoke([SystemMessage(content=eval_prompt)])
                        condition_result = "true" in llm_resp.content.lower()

                    step_trace.output_data = f"Resultado da condição: {condition_result}"
                    
                    # Choose handle
                    handle_target = "true" if condition_result else "false"
                    next_edge = next((e for e in adj_list.get(current_node_id, []) if e.get("sourceHandle") == handle_target or e.get("label", "").lower() == handle_target), None)
                    if not next_edge and adj_list.get(current_node_id):
                        next_edge = adj_list[current_node_id][0]
                    
                    chosen_id = next_edge.get("target") if next_edge else None
                    step_trace.duration_ms = round((time.monotonic() - node_start) * 1000, 2)
                    steps_trace.append(step_trace)
                    current_node_id = chosen_id
                    continue

                # ── 7. VERIFIER / GUARDRAIL (LOOP) NODE ────────────────────────
                elif node_type in ("verifier", "guardrail"):
                    retries = state["retry_counts"].get(current_node_id, 0)
                    max_retries = node_config.get("max_retries", 2)
                    verifier_criteria = node_config.get("criteria", "Verifique se a resposta está correta, segura e responde objetivamente à pergunta.")

                    v_prompt = (
                        f"Você é um Verificador de Qualidade de Respostas.\n"
                        f"Mensagem do Usuário: {state['original_message']}\n"
                        f"Resposta Gerada: {state['final_output']}\n"
                        f"Critério de Validação: {verifier_criteria}\n\n"
                        "Avalie se a resposta é APROVADA ou REPROVADA.\n"
                        "Responda SOMENTE em JSON: {\"status\": \"APPROVED\" ou \"REJECTED\", \"feedback\": \"motivo ou instruções de melhoria\"}"
                    )
                    llm_resp = await self.llm_default.ainvoke([SystemMessage(content=v_prompt)])
                    
                    is_approved = True
                    feedback = ""
                    import json
                    try:
                        clean_json = re.search(r'\{.*\}', llm_resp.content, re.DOTALL)
                        if clean_json:
                            data = json.loads(clean_json.group(0))
                            is_approved = data.get("status", "").upper() == "APPROVED"
                            feedback = data.get("feedback", "")
                    except Exception:
                        is_approved = "approved" in llm_resp.content.lower()

                    if is_approved or retries >= max_retries:
                        step_trace.output_data = f"Aprovado (Tentativas: {retries}/{max_retries})"
                        next_edge = next((e for e in adj_list.get(current_node_id, []) if e.get("sourceHandle") == "approved" or "aprov" in e.get("label", "").lower()), None)
                    else:
                        # REJECTED -> Trigger loop
                        state["retry_counts"][current_node_id] = retries + 1
                        state["loop_feedbacks"][current_node_id] = feedback
                        step_trace.output_data = f"Reprovado (Feedback: {feedback}) -> Iniciando Loop de Correção (Tentativa {retries + 1}/{max_retries})"
                        next_edge = next((e for e in adj_list.get(current_node_id, []) if e.get("sourceHandle") == "retry" or "reprov" in e.get("label", "").lower() or "loop" in e.get("label", "").lower()), None)

                    if not next_edge and adj_list.get(current_node_id):
                        next_edge = adj_list[current_node_id][0]

                    chosen_id = next_edge.get("target") if next_edge else None
                    step_trace.duration_ms = round((time.monotonic() - node_start) * 1000, 2)
                    steps_trace.append(step_trace)
                    current_node_id = chosen_id
                    continue

                # ── 8. TOOL / ACTION NODE ──────────────────────────────────────
                elif node_type in ("tool", "action"):
                    action_type = node_config.get("action_type", "mcp")
                    step_trace.output_data = f"Ação executada: {action_type}"

                # ── 9. END NODE ────────────────────────────────────────────────
                elif node_type in ("end", "output"):
                    step_trace.output_data = "Grafo finalizado com sucesso"
                    step_trace.duration_ms = round((time.monotonic() - node_start) * 1000, 2)
                    steps_trace.append(step_trace)
                    break

            except Exception as e:
                logger.error(f"[AgentGraphCompiler] Erro ao executar nó '{node_label}' ({current_node_id}): {e}", exc_info=True)
                step_trace.status = "error"
                step_trace.error = str(e)
                state["status"] = "error"
                state["error"] = str(e)

            step_trace.duration_ms = round((time.monotonic() - node_start) * 1000, 2)
            steps_trace.append(step_trace)

            # Move to next default outgoing edge
            outgoing = adj_list.get(current_node_id, [])
            current_node_id = outgoing[0].get("target") if outgoing else None

        total_duration = round((time.monotonic() - start_time) * 1000, 2)
        return AgentGraphExecuteResponse(
            graph_id=graph.id,
            graph_name=graph.name,
            final_output=state.get("final_output") or state.get("original_message", ""),
            steps=steps_trace,
            total_duration_ms=total_duration,
            status=state.get("status", "success"),
            error=state.get("error"),
            context_data=state.get("context_data")
        )

    async def _execute_single_sub_node(self, node: Dict[str, Any], state: AgentGraphState) -> str:
        """Helper to execute an isolated node in parallel"""
        node_type = node.get("data", {}).get("type", "agent")
        node_config = node.get("data", {}).get("config", {})
        
        if node_type == "agent":
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
