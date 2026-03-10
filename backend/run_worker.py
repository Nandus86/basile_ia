import asyncio
import logging
from arq import run_worker
from app.worker.settings import WorkerSettings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("basile_worker")

if __name__ == "__main__":
    logger.info("Starting Basile Worker with custom entrypoint...")
    # Run the ARQ worker programmatically
    # Since we pass the dict directly, ARQ should process the on_startup hooks.
    # To be absolutely sure, we can run our startup manually before starting the worker
    # but let's just use run_worker which explicitly takes the settings dict
    try:
        asyncio.run(run_worker(WorkerSettings))
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker stopped.")
