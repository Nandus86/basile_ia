"""
ARQ Worker Settings
Configures the worker process that consumes tasks from the Redis queue.
"""
from arq.connections import RedisSettings
from app.worker.tasks import process_message_task, process_message_structured_task
from app.config import settings


def parse_redis_url(url: str) -> dict:
    """Parse redis URL into host/port/db/password components."""
    # redis://localhost:6480/0 -> host=localhost, port=6480, database=0
    # redis://default:password@host:port/0 -> host, port, password, database
    url = url.replace("redis://", "")
    
    # Handle credentials: user:pass@host:port
    password = None
    if "@" in url:
        credentials, url = url.rsplit("@", 1)
        if ":" in credentials:
            _, password = credentials.split(":", 1)
        else:
            password = credentials
    
    # Handle database: host:port/db
    database = 0
    if "/" in url:
        url, db_str = url.rsplit("/", 1)
        try:
            database = int(db_str)
        except ValueError:
            database = 0
    
    # Handle host:port
    if ":" in url:
        host, port_str = url.split(":", 1)
        port = int(port_str)
    else:
        host = url
        port = 6379
    
    return {"host": host, "port": port, "database": database, "password": password}


def get_redis_settings() -> RedisSettings:
    """Build ARQ RedisSettings from app config."""
    parsed = parse_redis_url(settings.REDIS_URL)
    return RedisSettings(
        host=parsed["host"],
        port=parsed["port"],
        database=parsed["database"],
        password=parsed["password"],
    )


class WorkerSettings:
    """
    ARQ Worker configuration.
    This class is passed directly to `arq worker app.worker.settings.WorkerSettings`
    """
    # Task functions that the worker can execute
    functions = [
        process_message_task,
        process_message_structured_task,
    ]
    
    # Redis connection
    redis_settings = get_redis_settings()
    
    # Worker behavior
    max_jobs = 10              # Max concurrent jobs per worker
    job_timeout = 300          # 5 min timeout per job (LLM calls can be slow)
    keep_result = 3600         # Keep results for 1 hour
    retry_jobs = True          # Retry failed jobs
    max_tries = 3              # Max retry attempts
    
    # Health check
    health_check_interval = 30  # seconds
    
    # Queue name
    queue_name = "basile:queue"
