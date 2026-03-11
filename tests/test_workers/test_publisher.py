import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from aio_pika.exceptions import AMQPConnectionError

from app.models import KindEnum, StatusEnum
from app.workers.publisher import publish_transaction_event

pytestmark = pytest.mark.asyncio


def _make_mock_channel_and_exchange():
    exchange = AsyncMock()
    exchange.publish = AsyncMock()

    queue = AsyncMock()
    queue.bind = AsyncMock()

    dlq = AsyncMock()
    dlq.bind = AsyncMock()

    dlx = AsyncMock()

    channel = AsyncMock()
    channel.declare_exchange = AsyncMock(side_effect=[dlx, exchange])
    channel.declare_queue = AsyncMock(side_effect=[dlq, queue])

    return channel, exchange


class TestPublishTransactionEvent:
    async def test_publishes_message_successfully(self):
        channel, exchange = _make_mock_channel_and_exchange()

        connection = AsyncMock()
        connection.__aenter__ = AsyncMock(return_value=connection)
        connection.__aexit__ = AsyncMock(return_value=False)
        connection.channel = AsyncMock(return_value=channel)

        with patch("app.workers.publisher.aio_pika.connect_robust", return_value=connection):
            await publish_transaction_event(
                transaction_id=str(uuid.uuid4()),
                external_id=str(uuid.uuid4()),
                kind=KindEnum.CREDIT,
                status=StatusEnum.PROCESSED,
                amount=100.0,
            )

        exchange.publish.assert_awaited_once()

    async def test_amqp_connection_error_is_silenced(self):
        """AMQPConnectionError must not propagate (fire-and-forget)."""
        with patch(
            "app.workers.publisher.aio_pika.connect_robust",
            side_effect=AMQPConnectionError("no broker"),
        ):
            # Should not raise
            await publish_transaction_event(
                transaction_id=str(uuid.uuid4()),
                external_id=str(uuid.uuid4()),
                kind=KindEnum.DEBIT,
                status=StatusEnum.PROCESSED,
                amount=50.0,
            )

    async def test_timeout_error_is_silenced(self):
        """asyncio.TimeoutError must not propagate."""
        with patch(
            "app.workers.publisher.aio_pika.connect_robust",
            side_effect=asyncio.TimeoutError(),
        ):
            await publish_transaction_event(
                transaction_id=str(uuid.uuid4()),
                external_id=str(uuid.uuid4()),
                kind=KindEnum.CREDIT,
                status=StatusEnum.PROCESSED,
                amount=200.0,
            )

    async def test_unexpected_error_is_silenced(self):
        """Any unexpected exception must be caught and logged, not propagated."""
        with patch(
            "app.workers.publisher.aio_pika.connect_robust",
            side_effect=RuntimeError("unexpected"),
        ):
            await publish_transaction_event(
                transaction_id=str(uuid.uuid4()),
                external_id=str(uuid.uuid4()),
                kind=KindEnum.CREDIT,
                status=StatusEnum.PROCESSED,
                amount=10.0,
            )

    async def test_message_contains_correct_payload(self):
        """The published message body must contain the correct JSON payload."""
        import json

        channel, exchange = _make_mock_channel_and_exchange()

        connection = AsyncMock()
        connection.__aenter__ = AsyncMock(return_value=connection)
        connection.__aexit__ = AsyncMock(return_value=False)
        connection.channel = AsyncMock(return_value=channel)

        tx_id = str(uuid.uuid4())
        ext_id = str(uuid.uuid4())

        with patch("app.workers.publisher.aio_pika.connect_robust", return_value=connection):
            await publish_transaction_event(
                transaction_id=tx_id,
                external_id=ext_id,
                kind=KindEnum.CREDIT,
                status=StatusEnum.PROCESSED,
                amount=99.99,
            )

        published_message = exchange.publish.call_args[0][0]
        body = json.loads(published_message.body.decode())
        assert body["transaction_id"] == tx_id
        assert body["external_id"] == ext_id
        assert body["kind"] == KindEnum.CREDIT
        assert body["status"] == StatusEnum.PROCESSED
        assert body["amount"] == 99.99
