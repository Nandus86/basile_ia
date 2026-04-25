"""
Configurações do basile-ingress
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://basile:basile123@basile-postgres:5432/basile_db"
    REDIS_URL: str = "redis://basile-redis:6379"
    SECRET_KEY: str = "ingress-secret-key-change-in-production"
    
    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()