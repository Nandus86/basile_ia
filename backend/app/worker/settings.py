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


async def startup(ctx):
    """Called when ARQ worker starts."""
    import logging
    from app.worker.queue_consumer import start_rabbitmq_consumer
    import asyncio
    
    logger = logging.getLogger(__name__)
    logger.info("Starting RabbitMQ consumer...")
    
    # Fire and forget the consumer loop in the background, but attach an error handler
    task = asyncio.create_task(start_rabbitmq_consumer())
    
    def handle_exception(t):
        if not t.cancelled() and t.exception():
            logger.error(f"RabbitMQ consumer loop failed: {t.exception()}")
    
    task.add_done_callback(handle_exception)
    ctx["rabbitmq_task"] = task
    
async def shutdown(ctx):
    """Called when ARQ worker stops."""
    import logging
    from app.services.rabbitmq_service import rabbitmq_client
    logger = logging.getLogger(__name__)
    logger.info("Closing RabbitMQ connection...")
    await rabbitmq_client.disconnect()


class WorkerSettings:
    """ARQ Worker Settings"""
    functions = [
        process_message_task,
        process_message_structured_task,
    ]
    redis_settings = get_redis_settings()
    max_jobs = 10
    job_timeout = 300
    keep_result = 3600
    retry_jobs = True
    max_tries = 3
    health_check_interval = 30
    queue_name = "basile:queue"
    on_startup = startup
    on_shutdown = shutdown
