"""
RabbitMQ Service Client
"""
import json
import logging
from typing import Dict, Any, Optional
import aio_pika
from fastapi import BackgroundTasks

from app.config import settings

logger = logging.getLogger(__name__)


class RabbitMQClient:
    def __init__(self):
        self.connection: Optional[aio_pika.RobustConnection] = None
        self.channel: Optional[aio_pika.RobustChannel] = None
        self.webhook_queue_name = "webhook_process_queue"

    async def connect(self, retries=5, delay=5):
        """Connect to RabbitMQ and declare essential queues"""
        import asyncio
        for attempt in range(retries):
            try:
                self.connection = await aio_pika.connect_robust(
                    settings.RABBITMQ_URL,
                    client_properties={"connection_name": "Basile_Orch_Backend"}
                )
                self.channel = await self.connection.channel()
                # Declare the webhook queue
                await self.channel.declare_queue(
                    self.webhook_queue_name, 
                    durable=True,
                    arguments={"x-queue-type": "quorum"} # Quorum queue for better data safety
                )
                logger.info("Successfully connected to RabbitMQ and declared queues")
                return
            except Exception as e:
                logger.error(f"Failed to connect to RabbitMQ (attempt {attempt + 1}/{retries}): {str(e)}")
                if attempt < retries - 1:
                    await asyncio.sleep(delay)
                else:
                    logger.error("All retries to connect to RabbitMQ failed")

    async def disconnect(self):
        """Disconnect from RabbitMQ"""
        if self.channel:
            await self.channel.close()
        if self.connection:
            await self.connection.close()
        logger.info("Disconnected from RabbitMQ")

    async def publish_webhook_job(self, payload: Dict[str, Any], config_id: str, session_id: str, job_id: str) -> bool:
        """Publish a webhook payload to the processing queue"""
        if not self.channel:
            logger.error("Cannot publish message: RabbitMQ channel not initialized")
            return False

        message_body = {
            "payload": payload,
            "webhook_config_id": config_id,
            "session_id": session_id,
            "job_id": job_id
        }

        try:
            message = aio_pika.Message(
                body=json.dumps(message_body).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                content_type="application/json",
                message_id=job_id
            )

            await self.channel.default_exchange.publish(
                message,
                routing_key=self.webhook_queue_name
            )
            logger.info(f"Published webhook job {job_id} to queue")
            return True
        except Exception as e:
            logger.error(f"Error publishing to RabbitMQ: {str(e)}")
            return False


# Singleton instance
rabbitmq_client = RabbitMQClient()
