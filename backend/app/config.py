"""
Application Configuration
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings from environment variables"""
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://basile:basile123@localhost:5533/basile_db"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6480"
    
    # Weaviate
    WEAVIATE_URL: str = "http://localhost:8086"
    WEAVIATE_GRPC_PORT: int = 50051
    WEAVIATE_API_KEY: str = ""
    
    # RabbitMQ
    RABBITMQ_URL: str = "amqp://basile:basile_secret@localhost:5672/"
    
    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    
    # OpenAI
    OPENAI_API_KEY: str = ""
    VFS_STORAGE_PATH: str = "./storage/vfs"
    
    # Disparador Module
    DISPARADOR_SERVICE_URL: str = "http://basile-disparador:8000"
    
    # Weaviate configuration
    OPENROUTER_API_KEY: str = ""
    
    # LangSmith (Optional - for observability)
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "Basile_IA_Orch"
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"
    
    # Langfuse (Optional - for observability alongside LangSmith)
    LANGFUSE_ENABLED: bool = False
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings"""
    return Settings()


settings = get_settings()

import os
if settings.LANGCHAIN_TRACING_V2:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    if settings.LANGCHAIN_API_KEY:
        os.environ["LANGCHAIN_API_KEY"] = settings.LANGCHAIN_API_KEY
    if settings.LANGCHAIN_PROJECT:
        os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT
    if settings.LANGCHAIN_ENDPOINT:
        os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGCHAIN_ENDPOINT

import logging as _logging
_langfuse_logger = _logging.getLogger(__name__)
_langfuse_verified = False

# Set Langfuse env vars so the SDK can also auto-detect them
if settings.LANGFUSE_ENABLED:
    os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_SECRET_KEY
    os.environ["LANGFUSE_PUBLIC_KEY"] = settings.LANGFUSE_PUBLIC_KEY
    os.environ["LANGFUSE_HOST"] = settings.LANGFUSE_HOST
    _langfuse_logger.info(
        f"Langfuse enabled — host={settings.LANGFUSE_HOST}, "
        f"public_key={settings.LANGFUSE_PUBLIC_KEY[:12]}..."
    )

def get_langfuse_callback():
    """Create a fresh Langfuse CallbackHandler for LangChain tracing.
    
    Each invocation returns a NEW handler so that traces are properly separated.
    """
    global _langfuse_verified
    
    if not (settings.LANGFUSE_ENABLED and settings.LANGFUSE_SECRET_KEY and settings.LANGFUSE_PUBLIC_KEY):
        return None

    try:
        from langfuse.langchain import CallbackHandler
    except ImportError:
        _langfuse_logger.warning("Langfuse enabled but 'langfuse' package is not installed. Run: pip install langfuse")
        return None

    handler = CallbackHandler(
        secret_key=settings.LANGFUSE_SECRET_KEY,
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        host=settings.LANGFUSE_HOST,
    )
    
    # One-time auth check on first creation
    if not _langfuse_verified:
        try:
            handler.auth_check()
            _langfuse_logger.info("✅ Langfuse auth_check passed — connection OK")
            _langfuse_verified = True
        except Exception as e:
            _langfuse_logger.error(f"❌ Langfuse auth_check FAILED: {e}")
            return None

    return handler
