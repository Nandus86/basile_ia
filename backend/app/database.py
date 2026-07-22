"""
Database Configuration - PostgreSQL with SQLAlchemy Async
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from app.config import settings

import json
from uuid import UUID
from datetime import datetime

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, set):
            return list(obj)
        return super().default(obj)

def custom_serializer(obj):
    return json.dumps(obj, cls=CustomJSONEncoder, ensure_ascii=False)

# Create async engine with connection pooling for scalability
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_size=40,          # Base number of persistent connections
    max_overflow=20,       # Extra connections allowed beyond pool_size
    pool_pre_ping=True,    # Verify connections before use (handles stale connections)
    pool_recycle=1800,     # Recycle connections every 30 minutes
    pool_timeout=60,       # Wait up to 60s for a connection from pool
    json_serializer=custom_serializer,
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# Alias for background tasks
async_session_maker = AsyncSessionLocal

# Base class for models
Base = declarative_base()


async def get_db():
    """Dependency for getting database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
