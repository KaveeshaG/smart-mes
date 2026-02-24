"""
Message publisher for inter-service communication.
"""
import json
import aio_pika
from typing import Any
from ..models.events import BaseEvent

class MessagePublisher:
    def __init__(self, rabbitmq_url: str):
        self.rabbitmq_url = rabbitmq_url
        self.connection = None
        self.channel = None
    
    async def connect(self):
        self.connection = await aio_pika.connect_robust(self.rabbitmq_url)
        self.channel = await self.connection.channel()
    
    async def publish_event(self, event: BaseEvent, routing_key: str = ""):
        exchange = await self.channel.declare_exchange(
            "mes.events",
            aio_pika.ExchangeType.TOPIC,
            durable=True
        )
        
        message = aio_pika.Message(
            body=event.model_dump_json().encode(),
            content_type="application/json"
        )
        
        await exchange.publish(message, routing_key=routing_key)
    
    async def close(self):
        if self.connection:
            await self.connection.close()
