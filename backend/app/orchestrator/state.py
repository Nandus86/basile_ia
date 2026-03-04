"""
Supervisor State Definition for Multi-Agent Orchestration
"""
from typing import TypedDict, List, Optional, Dict, Any, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages


class SupervisorState(TypedDict, total=False):
    """State for the LangGraph Supervisor multi-agent orchestrator"""
    
    # Messages (with LangGraph message handling)
    messages: Annotated[List[BaseMessage], add_messages]
    
    # Input
    original_message: str
    session_id: str
    history: List[Dict[str, str]]
    requested_agent_id: Optional[str]
    user_access_level: str
    context_data: Optional[Dict[str, Any]]
    
    # Agent tracking
    current_agent_id: Optional[str]
    current_agent_name: Optional[str]
    current_agent_config: Optional[Dict[str, Any]]
    agents_used: List[str]
    
    # Supervisor control
    iteration: int
    max_iterations: int
    next_action: str  # "route", "execute", "collaborate", "end"
    needs_collaboration: bool
    collaboration_agents: List[str]
    
    # Processing
    context: List[Dict[str, Any]]
    rag_context: Optional[str]
    mcp_tools: List[Any]
    
    # Output
    agent_responses: Dict[str, str]
    final_response: Optional[str]
    error: Optional[str]


# Legacy state for backward compatibility
class OrchestratorState(TypedDict, total=False):
    """State for the LangGraph orchestrator (legacy)"""
    
    # Input
    message: str
    session_id: str
    history: List[Dict[str, str]]
    agent_id: Optional[str]
    user_access_level: str
    
    # Processing
    selected_agent: Optional[Dict[str, Any]]
    agent_model: Any
    context: List[Dict[str, Any]]
    mcp_triggered: bool
    mcp_result: Optional[Dict[str, Any]]
    
    # Output
    response: str
    agent_used: Optional[str]
    error: Optional[str]
