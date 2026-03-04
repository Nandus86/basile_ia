"""
Database Management Endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional

from app.database import get_db
from app.weaviate_client import get_weaviate, WeaviateClient
from app.schemas.database import (
    PostgresTablesResponse, PostgresTableInfo, PostgresStatsResponse,
    PostgresQueryRequest, PostgresQueryResponse,
    WeaviateClassesResponse, WeaviateClassInfo, WeaviateStatsResponse,
    WeaviateSearchRequest, WeaviateSearchResponse, WeaviatePurgeResponse
)

router = APIRouter()


# ==================== PostgreSQL Endpoints ====================

@router.get("/postgres/tables", response_model=PostgresTablesResponse)
async def list_postgres_tables(
    db: AsyncSession = Depends(get_db)
):
    """List all tables in PostgreSQL database"""
    query = text("""
        SELECT 
            table_name,
            table_schema
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)
    
    result = await db.execute(query)
    rows = result.fetchall()
    
    tables = [
        PostgresTableInfo(name=row[0], schema=row[1])
        for row in rows
    ]
    
    return PostgresTablesResponse(tables=tables, total=len(tables))


@router.get("/postgres/stats", response_model=PostgresStatsResponse)
async def get_postgres_stats(
    db: AsyncSession = Depends(get_db)
):
    """Get PostgreSQL database statistics"""
    # Database name
    db_name_result = await db.execute(text("SELECT current_database()"))
    db_name = db_name_result.scalar()
    
    # Database size
    size_result = await db.execute(
        text("SELECT pg_size_pretty(pg_database_size(current_database()))")
    )
    db_size = size_result.scalar()
    
    # Table count
    table_count_result = await db.execute(text("""
        SELECT COUNT(*) FROM information_schema.tables 
        WHERE table_schema = 'public'
    """))
    table_count = table_count_result.scalar()
    
    # Connection count
    conn_result = await db.execute(text("""
        SELECT COUNT(*) FROM pg_stat_activity 
        WHERE datname = current_database()
    """))
    conn_count = conn_result.scalar()
    
    return PostgresStatsResponse(
        database_name=db_name,
        database_size=db_size,
        table_count=table_count,
        connection_count=conn_count
    )


@router.post("/postgres/query", response_model=PostgresQueryResponse)
async def execute_postgres_query(
    request: PostgresQueryRequest,
    db: AsyncSession = Depends(get_db)
):
    """Execute a readonly SQL query"""
    # Safety check - only allow SELECT
    query_upper = request.query.strip().upper()
    if not query_upper.startswith("SELECT"):
        return PostgresQueryResponse(
            success=False,
            error="Only SELECT queries are allowed"
        )
    
    # Block dangerous keywords
    dangerous = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE"]
    for keyword in dangerous:
        if keyword in query_upper:
            return PostgresQueryResponse(
                success=False,
                error=f"Query contains forbidden keyword: {keyword}"
            )
    
    try:
        result = await db.execute(text(request.query))
        rows = result.fetchall()
        columns = list(result.keys())
        
        data = [dict(zip(columns, row)) for row in rows]
        
        return PostgresQueryResponse(
            success=True,
            columns=columns,
            rows=data,
            row_count=len(data)
        )
    except Exception as e:
        return PostgresQueryResponse(
            success=False,
            error=str(e)
        )


# ==================== Weaviate Endpoints ====================

@router.get("/weaviate/classes", response_model=WeaviateClassesResponse)
async def list_weaviate_classes():
    """List all Weaviate classes/collections"""
    weaviate = get_weaviate()
    
    try:
        class_names = await weaviate.get_classes()
        classes = []
        
        for name in class_names:
            stats = await weaviate.get_class_stats(name)
            classes.append(WeaviateClassInfo(
                name=name,
                object_count=stats.get("count", 0)
            ))
        
        return WeaviateClassesResponse(classes=classes, total=len(classes))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing Weaviate classes: {str(e)}"
        )


@router.get("/weaviate/stats", response_model=WeaviateStatsResponse)
async def get_weaviate_stats():
    """Get Weaviate statistics"""
    weaviate = get_weaviate()
    
    try:
        is_ready = await weaviate.is_ready()
        class_names = await weaviate.get_classes()
        
        total_objects = 0
        for name in class_names:
            stats = await weaviate.get_class_stats(name)
            total_objects += stats.get("count", 0)
        
        return WeaviateStatsResponse(
            is_ready=is_ready,
            class_count=len(class_names),
            total_objects=total_objects
        )
    except Exception as e:
        return WeaviateStatsResponse(
            is_ready=False,
            class_count=0,
            total_objects=0
        )


@router.post("/weaviate/search", response_model=WeaviateSearchResponse)
async def search_weaviate(
    request: WeaviateSearchRequest
):
    """Perform vector search in Weaviate"""
    weaviate = get_weaviate()
    
    try:
        results = await weaviate.search(
            class_name=request.class_name,
            query=request.query,
            limit=request.limit,
            properties=request.properties
        )
        
        return WeaviateSearchResponse(
            results=results,
            count=len(results)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )


@router.delete("/weaviate/purge/{class_name}", response_model=WeaviatePurgeResponse)
async def purge_weaviate_class(
    class_name: str
):
    """Delete all objects in a Weaviate class"""
    weaviate = get_weaviate()
    
    try:
        success = await weaviate.purge_class(class_name)
        
        return WeaviatePurgeResponse(
            success=success,
            class_name=class_name,
            message=f"Class {class_name} purged successfully" if success else "Purge failed"
        )
    except Exception as e:
        return WeaviatePurgeResponse(
            success=False,
            class_name=class_name,
            message=str(e)
        )
