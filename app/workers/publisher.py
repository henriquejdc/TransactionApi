import asyncio
import json
from typing import Any

import aio_pika
from aio_pika.exceptions import AMQPConnectionError

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

EXCHANGE_NAME = "transactions.exchange"
QUEUE_NAME = "transactions.queue"
DLX_NAME = "transactions.dlx"
DLQ_NAME = "transactions.dlq"
ROUTING_KEY = "transaction.created"
MESSAGE_TTL_MS = 60_000


async def _declare_topology(channel: aio_pika.abc.AbstractChannel) -> aio_pika.Exchange:
    """Declare exchange, DLX/DLQ and main queue with DLQ binding."""
    dlx = await channel.declare_exchange(DLX_NAME, aio_pika.ExchangeType.FANOUT, durable=True)
    dlq = await channel.declare_queue(DLQ_NAME, durable=True)
    await dlq.bind(dlx)

    exchange = await channel.declare_exchange(
        EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
    )

    queue = await channel.declare_queue(
        QUEUE_NAME,
        durable=True,
        arguments={
            "x-dead-letter-exchange": DLX_NAME,
            "x-message-ttl": MESSAGE_TTL_MS,
        },
    )
    await queue.bind(exchange, routing_key="transaction.#")

    return exchange


async def publish_transaction_event(**payload: Any) -> None:
    """
    Publish a transaction event to RabbitMQ asynchronously.
    Errors are logged but never propagate to the caller (fire-and-forget).
    """
    settings = get_settings()
    try:
        connection = await aio_pika.connect_robust(settings.RABBITMQ_URL, timeout=5)
        async with connection:
            channel = await connection.channel()
            exchange = await _declare_topology(channel)

            body = json.dumps(payload, default=str).encode()
            message = aio_pika.Message(
                body=body,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                content_type="application/json",
            )
            await exchange.publish(message, routing_key=ROUTING_KEY)
            logger.info(
                "Event published to RabbitMQ | routing_key=%s payload=%s",
                ROUTING_KEY,
                payload,
            )
    except AMQPConnectionError as exc:
        logger.error("Failed to connect to RabbitMQ — event not published: %s", exc)
    except asyncio.TimeoutError:
        logger.error("RabbitMQ publish timed out — event not published")
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error publishing to RabbitMQ: %s", exc)
