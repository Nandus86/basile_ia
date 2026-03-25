"""
Webhook Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class WebhookRequest(BaseModel):
    """Generic webhook request payload"""
    source: str = Field(..., description="Source of the webhook (e.g., 'whatsapp', 'telegram')")
    event_type: str = Field(default="message", description="Type of event")
    message: str = Field(..., description="Message content")
    sender_id: str = Field(..., description="Sender identifier")
    sender_name: Optional[str] = Field(None, description="Sender name")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")
    timestamp: Optional[datetime] = Field(None, description="Event timestamp")


class WebhookResponse(BaseModel):
    """Webhook response"""
    success: bool = True
    message: str
    data: Optional[Dict[str, Any]] = None


class ProcessRequest(BaseModel):
    """Process request - synchronous processing"""
    message: str = Field(..., description="Message to process")
    session_id: str = Field(..., description="Session identifier for conversation context")
    agent_id: Optional[str] = Field(None, description="Specific agent to use")
    user_access_level: str = Field(default="normal", description="User access level (minimum/normal/pro/premium)")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    context_data: Optional[Dict[str, Any]] = Field(default=None, description="Dados contextuais estruturados para o agente (ex: dados do usuário, da igreja, etc.)")
    transition_data: Optional[Dict[str, Any]] = Field(default=None, description="Dados de metadados para controle do fluxo que o LLM não precisa ler.")
    callback_url: Optional[str] = Field(None, description="URL to send the result to when processing finishes")

    model_config = {"extra": "allow"}


class ProcessResponse(BaseModel):
    """Process response"""
    response: str
    agent_used: Optional[str] = None
    processing_time_ms: Optional[float] = None
    transition_data: Optional[Dict[str, Any]] = Field(default=None, description="Dados de transição passados no request")
    last_agent: Optional[str] = Field(default=None, description="Nome do último agente que atendeu esta sessão")


class AsyncProcessResponse(BaseModel):
    """Response for async job submission"""
    job_id: str = Field(..., description="ID do job na fila para consulta posterior")
    status: str = Field(default="queued", description="Status inicial do job")
    message: str = Field(default="Job enfileirado com sucesso")


class JobStatusResponse(BaseModel):
    """Response for job status check"""
    job_id: str
    status: str = Field(..., description="queued | in_progress | completed | failed | not_found")
    result: Optional[Any] = Field(None, description="Resultado do job quando completo")
    agent_used: Optional[str] = Field(None, description="Agente utilizado para a resposta")
    transition_data: Optional[Dict[str, Any]] = Field(default=None, description="Dados de transição passados no request")

    model_config = {"extra": "allow"}

class ChatFeedbackRequest(BaseModel):
    """Payload para envio de feedback (RLHF - polegar cima/baixo)"""
    agent_id: str = Field(..., description="ID do Agente que gerou a resposta")
    session_id: str = Field(..., description="Sessão do chat")
    feedback_type: str = Field(..., description="'positive' ou 'negative'")
    user_message: str = Field(..., description="Mensagem do usuário que gerou a resposta")
    agent_response: str = Field(..., description="Resposta do agente que está recebendo feedback")
    correction_note: Optional[str] = Field(None, description="Opcional: Nota do humano explicando o erro ou acerto")

class ChatFeedbackResponse(BaseModel):
    """Resposta ao salvar feedback"""
    success: bool
    message: str
    rule_extracted: Optional[str] = None
