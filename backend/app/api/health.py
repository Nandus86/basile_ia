"""
Health Check Endpoints
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.redis_client import get_redis, RedisClient
from app.weaviate_client import get_weaviate, WeaviateClient

router = APIRouter()


@router.get("/health")
async def health_check():
    """Basic health check"""
    return {
        "status": "healthy",
        "service": "basile-ia-orch"
    }


@router.get("/health/dependencies")
async def health_dependencies(
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """Check all dependencies health"""
    dependencies = {}
    
    # Check PostgreSQL
    try:
        await db.execute(text("SELECT 1"))
        dependencies["postgresql"] = {"status": "healthy"}
    except Exception as e:
        dependencies["postgresql"] = {"status": "unhealthy", "error": str(e)}
    
    # Check Redis
    try:
        redis_ok = await redis.ping()
        dependencies["redis"] = {"status": "healthy" if redis_ok else "unhealthy"}
    except Exception as e:
        dependencies["redis"] = {"status": "unhealthy", "error": str(e)}
    
    # Check Weaviate
    try:
        weaviate = get_weaviate()
        weaviate_ok = await weaviate.is_ready()
        dependencies["weaviate"] = {"status": "healthy" if weaviate_ok else "unhealthy"}
    except Exception as e:
        dependencies["weaviate"] = {"status": "unhealthy", "error": str(e)}
    
    # Overall status
    all_healthy = all(d.get("status") == "healthy" for d in dependencies.values())
    
    return {
        "status": "healthy" if all_healthy else "degraded",
        "dependencies": dependencies
    }
