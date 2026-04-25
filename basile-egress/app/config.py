"""
Configurações do basile-egress
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://basile:basile123@basile-postgres:5432/basile_db"
    REDIS_URL: str = "redis://basile-redis:6379"
    SECRET_KEY: str = "egress-secret-key-change-in-production"
    
    DEFAULT_WEBHOOK_TIMEOUT: int = 30
    DEFAULT_RETRY_MAX: int = 3
    DEFAULT_RETRY_DELAYS: list = [1000, 5000, 15000]
    
    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()