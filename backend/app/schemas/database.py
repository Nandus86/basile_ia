"""
Database Management Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


# PostgreSQL Schemas
class PostgresTableInfo(BaseModel):
    """Table information"""
    name: str
    schema_name: str = Field("public", alias="schema")
    row_count: Optional[int] = None
    size_bytes: Optional[int] = None


class PostgresTablesResponse(BaseModel):
    """List of tables"""
    tables: List[PostgresTableInfo]
    total: int


class PostgresStatsResponse(BaseModel):
    """PostgreSQL statistics"""
    database_name: str
    database_size: str
    table_count: int
    connection_count: int


class PostgresQueryRequest(BaseModel):
    """Query request (readonly)"""
    query: str = Field(..., description="SQL query (SELECT only)")
    params: Optional[Dict[str, Any]] = None


class PostgresQueryResponse(BaseModel):
    """Query response"""
    success: bool
    columns: List[str] = []
    rows: List[Dict[str, Any]] = []
    row_count: int = 0
    error: Optional[str] = None


# Weaviate Schemas
class WeaviateClassInfo(BaseModel):
    """Weaviate class information"""
    name: str
    object_count: int


class WeaviateClassesResponse(BaseModel):
    """List of Weaviate classes"""
    classes: List[WeaviateClassInfo]
    total: int


class WeaviateStatsResponse(BaseModel):
    """Weaviate statistics"""
    is_ready: bool
    class_count: int
    total_objects: int


class WeaviateSearchRequest(BaseModel):
    """Vector search request"""
    class_name: str
    query: str
    limit: int = Field(default=5, ge=1, le=100)
    properties: Optional[List[str]] = None


class WeaviateSearchResponse(BaseModel):
    """Vector search response"""
    results: List[Dict[str, Any]]
    count: int


class WeaviatePurgeResponse(BaseModel):
    """Purge response"""
    success: bool
    class_name: str
    message: str
