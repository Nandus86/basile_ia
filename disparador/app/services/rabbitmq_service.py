import json
import logging
import aio_pika
from aio_pika.abc import AbstractRobustConnection
import asyncio

from app.config import settings

logger = logging.getLogger(__name__)

class DisparadorRabbitMQ:
    def __init__(self):
        self.connection_url = settings.RABBITMQ_URL
        self.connection: AbstractRobustConnection | None = None
        self.channel = None

    async def connect(self):
        """Establish robust connection to RabbitMQ"""
        if not self.connection or self.connection.is_closed:
            try:
                self.connection = await aio_pika.connect_robust(
                    self.connection_url,
                    client_properties={"connection_name": "Disparador Webhook API"}
                )
                self.channel = await self.connection.channel()
                await self.channel.set_qos(prefetch_count=10)
                logger.info("Connected to RabbitMQ for Disparador reliably.")
            except Exception as e:
                logger.error(f"Failed to connect to RabbitMQ for Disparador: {e}")
                self.connection = None
                self.channel = None

    async def disconnect(self):
        """Close connection"""
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            logger.info("RabbitMQ for Disparador connection closed.")

    async def declare_dispatch_queue(self, type_id: str, queue_id: str):
        if not self.channel:
            await self.connect()
            if not self.channel:
                raise Exception("Cannot connect to RabbitMQ to declare queue")

        queue_name = f"disp_{type_id}_{queue_id}"
        dlq_name = f"disp_dlq_{type_id}_{queue_id}"

        # Declare DLQ
        await self.channel.declare_queue(dlq_name, durable=True)
        
        # Declare main queue with DLX
        await self.channel.declare_queue(
            queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": dlq_name,
            }
        )
        return queue_name, dlq_name
        
    async def republish_contact(self, queue_name: str, payload_json: str):
        if not self.channel:
            await self.connect()
            if not self.channel:
                return False

        try:
            message = aio_pika.Message(
                body=payload_json.encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )
            await self.channel.default_exchange.publish(
                message,
                routing_key=queue_name
            )
            return True
        except Exception as e:
            logger.error(f"Failed to republish contact: {e}")
            return False

    async def publish_contact(self, type_id: str, queue_id: str, contact_payload: dict):
        if not self.channel:
            await self.connect()
            if not self.channel:
                return False

        queue_name, _ = await self.declare_dispatch_queue(type_id, queue_id)
        
        try:
            message_body = json.dumps(contact_payload)
            message = aio_pika.Message(
                body=message_body.encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )
            await self.channel.default_exchange.publish(
                message,
                routing_key=queue_name
            )
            return True
        except Exception as e:
            logger.error(f"Failed to publish contact to Disparador queue: {e}")
            return False

disparador_rmq = DisparadorRabbitMQ()
