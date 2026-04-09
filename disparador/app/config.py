import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://basile:basile123@basile-postgres:5432/basile_db"
    REDIS_URL: str = "redis://basile-redis:6379"
    RABBITMQ_URL: str = "amqp://basile:basile_secret@basile-rabbitmq:5672/"
    BASILE_API_URL: str = "http://basile-backend:8000"

    class Config:
        env_file = ".env"

settings = Settings()
