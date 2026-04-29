"""
Configurações do basile-ingress
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://basile:basile123@basile-postgres:5432/basile_db"
    REDIS_URL: str = "redis://basile-redis:6379"
    SECRET_KEY: str = "ingress-secret-key-change-in-production"

    # Forwarding
    FORWARD_TIMEOUT: int = 120  # seconds — must be long enough for sync agent processing

    # Dispatcher (background retry loop)
    DISPATCH_INTERVAL_SECONDS: int = 30  # how often the dispatcher scans queues
    DISPATCH_MAX_RETRIES: int = 50  # total retry attempts before dropping
    DISPATCH_RETRY_DELAYS: list = [5, 10, 30, 60, 120]  # seconds between retries (cycles through)

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()