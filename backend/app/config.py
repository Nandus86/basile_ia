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
    
    # RabbitMQ
    RABBITMQ_URL: str = "amqp://basile:basile_secret@localhost:5672/"
    
    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    
    # OpenAI
    OPENAI_API_KEY: str = ""
    
    # OpenRouter
    OPENROUTER_API_KEY: str = ""
    
    # LangSmith (Optional - for observability)
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "Basile_IA_Orch"
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings"""
    return Settings()


settings = get_settings()
