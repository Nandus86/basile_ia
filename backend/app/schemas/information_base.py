from pydantic import BaseModel, Field, UUID4, validator
from typing import Optional, List, Dict, Any
from datetime import datetime

class InformationBaseBase(BaseModel):
    name: str = Field(..., max_length=100, description="Nome de exibição da base")
    code: str = Field(..., max_length=100, description="Código único usado pelo webhook (id_base)")
    content_schema: Optional[Dict[str, Any]] = Field(None, description="Schema de como os dados de conteúdo textual serão recebidos")
    metadata_schema: Optional[Dict[str, Any]] = Field(None, description="Schema do metadata que pode ser filtrado")
    is_active: bool = True

class InformationBaseCreate(InformationBaseBase):
    pass

class InformationBaseUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    code: Optional[str] = Field(None, max_length=100)
    content_schema: Optional[Dict[str, Any]] = None
    metadata_schema: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

class InformationBaseResponse(InformationBaseBase):
    id: UUID4
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class InformationBaseSummary(BaseModel):
    id: UUID4
    name: str
    code: str
    is_active: bool

    class Config:
        from_attributes = True

class InformationBaseList(BaseModel):
    information_bases: List[InformationBaseSummary]
    total: int

class InformationBaseWebhookRequest(BaseModel):
    """
    Payload required for webhook to insert new documents to Weaviate for a specific contact
    """
    id_base: str = Field(..., description="The code of the InformationBase")
    id: str = Field(..., description="The contact id (user_id) owning this info")
    data: Dict[str, Any] = Field(..., description="The payload according to content_schema and metadata_schema")

class InformationBaseWebhookResponse(BaseModel):
    success: bool
    message: str
