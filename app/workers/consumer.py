import asyncio
import json
import signal

import aio_pika

from app.core.config import get_settings
from app.core.logging import get_logger
from app.workers.publisher import DLQ_NAME, DLX_NAME, EXCHANGE_NAME, QUEUE_NAME

logger = get_logger(__name__)


async def _declare_topology(channel: aio_pika.abc.AbstractChannel) -> aio_pika.Queue:
    """Re-declare topology (idempotent) and return the main queue."""
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
            "x-message-ttl": 60_000,
        },
    )
    await queue.bind(exchange, routing_key="transaction.#")
    return queue


async def process_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
    async with message.process(requeue=False):
        try:
            payload = json.loads(message.body.decode())
            logger.info("Received transaction event | payload=%s", payload)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to process message: %s | body=%s", exc, message.body)
            raise


async def main() -> None:
    settings = get_settings()
    logger.info("Starting RabbitMQ consumer…")

    connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    loop = asyncio.get_event_loop()

    def _shutdown(*_):
        logger.info("Shutting down consumer…")
        loop.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)
        queue = await _declare_topology(channel)
        await queue.consume(process_message)
        logger.info("Consumer ready — waiting for messages…")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
