from sqlalchemy import Column, String, Boolean, Integer, JSON, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime, timezone

from app.database import Base

class DispatcherConfig(Base):
    __tablename__ = "dispatcher_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    path = Column(String(255), nullable=False, unique=True, index=True)
    
    # Autenticação
    api_key = Column(String(500), nullable=True)  # system.apikey para validar requests
    
    # Botões
    buttons_enabled = Column(Boolean, default=False)
    buttons = Column(JSON, default=[])  # [{label: str, value: str, action: str}, ...]
    
    # Imagem
    image_enabled = Column(Boolean, default=False)
    
    # Controle de mensagens
    messages_per_batch = Column(Integer, default=1)
    
    # Agente
    agent_id = Column(UUID(as_uuid=True), nullable=True)
    
    # Janela de horário (HH:mm)
    start_time = Column(String(5), default="08:00")
    end_time = Column(String(5), default="22:00")
    
    # Delays
    start_delay_seconds = Column(Integer, default=0)
    min_variation_seconds = Column(Integer, default=5)
    max_variation_seconds = Column(Integer, default=15)
    
    # Triggers (tags para inserir na mensagem como chave de saída)
    triggers = Column(JSON, default=[])
    
    # Index (0 a index_max, sem repetição por ciclo)
    index_max = Column(Integer, default=5)
    
    # Progress callback (opcional)
    progress_callback_url = Column(String(500), nullable=True)
    target_endpoint = Column(String(500), nullable=True)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
