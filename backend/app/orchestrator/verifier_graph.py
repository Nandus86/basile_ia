"""
LangGraph Verifier / Critic Graph
Performs deterministic verification of tool execution results and semantic validation of agent responses.
Runs up to MAX_VERIFICATION_ATTEMPTS (3).
"""
import json
import logging
from typing import TypedDict, List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field

from langchain_core.messages import BaseMessage, ToolMessage, AIMessage, SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)

MAX_VERIFICATION_ATTEMPTS = 3


class VerificationResult(BaseModel):
    """Structured output for semantic response validation."""
    is_valid: bool = Field(description="True se a resposta atende adequadamente ao pedido e usou os dados de ferramentas de forma correta.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Nível de confiança na validação (0 a 1).")
    reasoning: str = Field(description="Justificativa sucinta sobre a validação.")
    action: Literal["APPROVE", "RETRY"] = Field(description="Ação recomendada: APPROVE se a resposta está OK, RETRY se precisa de correção.")
    correction_guidance: Optional[str] = Field(default=None, description="Instruções claras e específicas do que o agente deve corrigir caso action == RETRY.")


class VerifierState(TypedDict, total=False):
    """State schema for the Verifier / Critic Graph"""
    original_message: str
    agent_config: Dict[str, Any]
    messages: List[Any]
    response: str
    verification_attempt: int
    status: str  # "SUCCESS" | "NEED_CORRECTION" | "MAX_ATTEMPTS_REACHED"
    correction_instruction: Optional[str]
    validation_details: Optional[Dict[str, Any]]
    llm: Optional[Any]


def analyze_tool_results(state: VerifierState) -> VerifierState:
    """
    Deterministic Node: Inspects ToolMessages looking for errors, exceptions, or empty/failed status.
    Requires NO LLM call for maximum speed and zero extra token cost.
    """
    messages = state.get("messages", [])
    attempt = state.get("verification_attempt", 0)
    
    if attempt >= MAX_VERIFICATION_ATTEMPTS:
        logger.warning(f"[VerifierGraph] ⚠️ Atingido limite máximo de verificações ({MAX_VERIFICATION_ATTEMPTS}). Liberando resposta.")
        state["status"] = "MAX_ATTEMPTS_REACHED"
        return state

    tool_errors = []
    
    for msg in messages:
        # Check ToolMessages or tool-like payload dictionaries
        if isinstance(msg, ToolMessage) or (isinstance(msg, dict) and msg.get("role") == "tool"):
            content = msg.content if isinstance(msg, ToolMessage) else msg.get("content", "")
            tool_name = getattr(msg, "name", None) or (msg.get("name") if isinstance(msg, dict) else "ferramenta")
            
            content_str = str(content)
            
            # Check common deterministic failure signatures
            has_error_keyword = any(err in content_str.lower() for err in [
                "error", "erro:", "exception", "failed", "statuscode': 4", "statuscode': 5",
                "tool call blocked", "timeout", "unauthorized", "bad request", "not found"
            ])
            
            # Check JSON payloads for error fields
            is_json_error = False
            try:
                if content_str.strip().startswith("{") and content_str.strip().endswith("}"):
                    data = json.loads(content_str)
                    if isinstance(data, dict):
                        if data.get("error") or data.get("err") or data.get("status") == "error" or data.get("success") is False:
                            is_json_error = True
            except Exception:
                pass
                
            if has_error_keyword or is_json_error:
                tool_errors.append(f"Ferramenta '{tool_name}' retornou erro: {content_str[:300]}")
    
    if tool_errors:
        err_msg = "\n".join(tool_errors)
        logger.info(f"[VerifierGraph] 🚨 Falha determinística detectada em ferramentas:\n{err_msg}")
        state["status"] = "NEED_CORRECTION"
        state["correction_instruction"] = (
            f"AUDITORIA DE SISTEMA (Tentativa {attempt + 1}/{MAX_VERIFICATION_ATTEMPTS}):\n"
            f"A execução de ferramentas apresentou os seguintes erros:\n{err_msg}\n"
            f"Por favor, revise os parâmetros informados, corrija a chamada da ferramenta ou tente uma abordagem alternativa para obter o resultado desejado."
        )
        return state
        
    state["status"] = "PENDING_SEMANTIC_VALIDATION"
    return state


async def validate_response_semantics(state: VerifierState) -> VerifierState:
    """
    LLM Node: Evaluates if the agent's final response effectively answers the user's message
    and correctly utilizes tool outputs.
    Uses the exact same LLM instance supplied by the orchestrator/agent.
    """
    # If deterministic check already caught an error, skip LLM check
    if state.get("status") == "NEED_CORRECTION" or state.get("status") == "MAX_ATTEMPTS_REACHED":
        return state

    attempt = state.get("verification_attempt", 0)
    original_msg = state.get("original_message", "")
    response = state.get("response", "")
    llm = state.get("llm")
    
    if not llm or not original_msg or not response:
        state["status"] = "SUCCESS"
        return state

    try:
        # Bind structured output
        verifier_llm = llm.with_structured_output(VerificationResult)
        
        prompt = f"""Você é um auditor rigoroso de qualidade de agentes IA.
        
SOLICITAÇÃO ORIGINAL DO USUÁRIO:
"{original_msg}"

RESPOSTA GERADA PELO AGENTE:
"{response}"

TAREFA DE AUDITORIA:
1. Avalie se a resposta atende diretamente à solicitação do usuário.
2. Se a solicitação exigia busca/ação via ferramenta e o agente respondeu sem dados ou de forma genérica/evasiva, marque como RETRY.
3. Se a resposta for suficiente, precisa e completa, marque como APPROVE.

Responda rigorosamente no formato de dados estruturado."""

        config = RunnableConfig(
            run_name="Verifier Semantic Check",
            metadata={"attempt": attempt}
        )
        
        result: VerificationResult = await verifier_llm.ainvoke(
            [SystemMessage(content=prompt)],
            config=config
        )
        
        state["validation_details"] = result.dict() if hasattr(result, "dict") else {}
        
        if result and not result.is_valid and result.action == "RETRY":
            logger.info(f"[VerifierGraph] 🔍 Validação semântica reprovou resposta: {result.reasoning}")
            state["status"] = "NEED_CORRECTION"
            guidance = result.correction_guidance or result.reasoning
            state["correction_instruction"] = (
                f"AUDITORIA SEMÂNTICA (Tentativa {attempt + 1}/{MAX_VERIFICATION_ATTEMPTS}):\n"
                f"A resposta gerada foi considerada incompleta ou inconsistente: {result.reasoning}.\n"
                f"Instrução de correção: {guidance}"
            )
        else:
            logger.info("[VerifierGraph] ✅ Resposta aprovada na auditoria semântica.")
            state["status"] = "SUCCESS"
            
    except Exception as e:
        logger.warning(f"[VerifierGraph] Erro ao executar validação semântica (aprovando por tolerância): {e}")
        state["status"] = "SUCCESS"

    return state


def route_verification(state: VerifierState) -> str:
    """Conditional Edge: Decides whether to request agent correction or end verification."""
    status = state.get("status", "SUCCESS")
    attempt = state.get("verification_attempt", 0)
    
    if status == "NEED_CORRECTION" and attempt < MAX_VERIFICATION_ATTEMPTS:
        return "need_correction"
    return "approved"


def build_verifier_graph() -> StateGraph:
    """Builds and compiles the Verifier / Critic LangGraph."""
    graph = StateGraph(VerifierState)
    
    graph.add_node("analyze_tools", analyze_tool_results)
    graph.add_node("validate_semantics", validate_response_semantics)
    
    graph.set_entry_point("analyze_tools")
    
    graph.add_edge("analyze_tools", "validate_semantics")
    
    graph.add_conditional_edges(
        "validate_semantics",
        route_verification,
        {
            "need_correction": END,
            "approved": END
        }
    )
    
    return graph.compile()


# Single compiled instance for reuse
verifier_graph_compiled = build_verifier_graph()


async def run_verifier(
    original_message: str,
    response: str,
    messages: List[Any],
    agent_config: Dict[str, Any],
    llm: Any,
    verification_attempt: int = 0
) -> Dict[str, Any]:
    """
    Runner function to execute the Verifier Graph.
    
    Returns:
        Dict with status ("SUCCESS" | "NEED_CORRECTION" | "MAX_ATTEMPTS_REACHED")
        and correction_instruction if status == "NEED_CORRECTION".
    """
    initial_state: VerifierState = {
        "original_message": original_message,
        "response": response,
        "messages": messages,
        "agent_config": agent_config,
        "verification_attempt": verification_attempt,
        "status": "PENDING",
        "correction_instruction": None,
        "validation_details": None,
        "llm": llm
    }
    
    result = await verifier_graph_compiled.ainvoke(initial_state)
    return {
        "status": result.get("status", "SUCCESS"),
        "correction_instruction": result.get("correction_instruction"),
        "validation_details": result.get("validation_details")
    }
