"""
Agent Graph Pydantic Schemas - Validation and Serialization for Multi-Agent Graphs
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID


class AgentGraphBase(BaseModel):
    """Base schema for Agent Graph"""
    name: str = Field(..., min_length=1, max_length=255, description="Nome do Grafo de Agentes")
    description: Optional[str] = Field(None, description="Descrição do objetivo do grafo")
    is_active: bool = Field(True, description="Status de ativação do grafo")
    definition: Dict[str, Any] = Field(default_factory=dict, description="Estrutura de nós, arestas e posições do VueFlow")
    recursion_limit: int = Field(25, ge=1, le=100, description="Limite máximo de iterações/recursão do grafo")
    timeout_seconds: int = Field(60, ge=5, le=300, description="Timeout máximo de execução em segundos")


class AgentGraphCreate(AgentGraphBase):
    """Schema for creating a new Agent Graph"""
    pass


class AgentGraphUpdate(BaseModel):
    """Schema for updating an existing Agent Graph"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    definition: Optional[Dict[str, Any]] = None
    recursion_limit: Optional[int] = Field(None, ge=1, le=100)
    timeout_seconds: Optional[int] = Field(None, ge=5, le=300)


class AgentGraphSummary(BaseModel):
    """Summary representation of an Agent Graph"""
    id: UUID
    name: str
    description: Optional[str] = None
    is_active: bool = True
    node_count: int = 0
    recursion_limit: int = 25
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentGraphResponse(AgentGraphBase):
    """Full representation of an Agent Graph"""
    id: UUID
    node_count: int = 0
    assigned_agent_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentGraphList(BaseModel):
    """List of Agent Graphs"""
    graphs: List[AgentGraphSummary]
    total: int


class AgentGraphExecuteRequest(BaseModel):
    """Request payload to test or trigger an Agent Graph"""
    message: str = Field(..., min_length=1, description="Mensagem de entrada para o grafo")
    history: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Histórico de mensagens para conversas multi-turnos")
    context_data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Dados de contexto adicionais (ex: dados da igreja, contato)")
    session_id: Optional[str] = Field(None, description="ID da sessão para manter memória/histórico")
    definition: Optional[Dict[str, Any]] = Field(None, description="Definição temporária do grafo vinda do canvas para testes antes de salvar")


class AgentGraphStepTrace(BaseModel):
    """Execution trace of an individual node in the graph"""
    node_id: str
    node_type: str
    node_label: str
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    input_data: Optional[Any] = None
    output_data: Optional[Any] = None
    duration_ms: float = 0.0
    status: str = "success"  # success, error, skipped
    error: Optional[str] = None
    feedback: Optional[str] = None


class AgentGraphExecuteResponse(BaseModel):
    """Response payload of an Agent Graph execution with step trace"""
    graph_id: UUID
    graph_name: str
    final_output: str
    steps: List[AgentGraphStepTrace] = []
    total_duration_ms: float = 0.0
    status: str = "success"  # success, error, timeout
    error: Optional[str] = None
    context_data: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None
