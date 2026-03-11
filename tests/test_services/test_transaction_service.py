import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import PartnerUnavailableError, TransactionAlreadyProcessedError
from app.models.transaction import KindEnum, StatusEnum
from app.schemas.transaction import TransactionRequest
from app.services.transaction_service import TransactionService

pytestmark = pytest.mark.asyncio


def _make_service(session, partner_client=None):
    return TransactionService(session=session, partner_client=partner_client)


class TestCreateTransaction:
    async def test_success_credit(self, db_session, mock_publisher):
        """Happy path: credit transaction is processed and response is returned."""
        partner_tx_id = str(uuid.uuid4())
        partner_client = AsyncMock()
        partner_client.send_transaction = AsyncMock(
            return_value={"transaction_id": partner_tx_id, "status": "approved"}
        )

        service = _make_service(db_session, partner_client)
        request = TransactionRequest(
            external_id=uuid.uuid4(), amount=Decimal("150.00"), kind=KindEnum.CREDIT
        )

        response = await service.create_transaction(request)

        assert response.external_id == request.external_id
        assert response.kind == KindEnum.CREDIT
        assert response.status == StatusEnum.PROCESSED
        assert response.partner_transaction_id == partner_tx_id
        partner_client.send_transaction.assert_awaited_once()
        mock_publisher.assert_awaited_once()

    async def test_success_debit(self, db_session, mock_publisher):
        """Happy path: debit transaction is processed successfully."""
        partner_client = AsyncMock()
        partner_client.send_transaction = AsyncMock(
            return_value={"transaction_id": str(uuid.uuid4()), "status": "approved"}
        )

        service = _make_service(db_session, partner_client)
        request = TransactionRequest(
            external_id=uuid.uuid4(), amount=Decimal("50.00"), kind=KindEnum.DEBIT
        )

        response = await service.create_transaction(request)

        assert response.kind == KindEnum.DEBIT
        assert response.status == StatusEnum.PROCESSED

    async def test_idempotency_raises_on_duplicate(self, db_session, mock_publisher):
        """Duplicate external_id must raise TransactionAlreadyProcessedError."""
        partner_client = AsyncMock()
        partner_client.send_transaction = AsyncMock(
            return_value={"transaction_id": str(uuid.uuid4())}
        )

        service = _make_service(db_session, partner_client)
        request = TransactionRequest(
            external_id=uuid.uuid4(), amount=Decimal("10.00"), kind=KindEnum.CREDIT
        )

        await service.create_transaction(request)

        with pytest.raises(TransactionAlreadyProcessedError) as exc_info:
            await service.create_transaction(request)

        assert str(request.external_id) in exc_info.value.message

    async def test_partner_unavailable_marks_failed(self, db_session, mock_publisher):
        """When partner raises PartnerUnavailableError, transaction is saved as FAILED."""
        partner_client = AsyncMock()
        partner_client.send_transaction = AsyncMock(
            side_effect=PartnerUnavailableError("Partner is down")
        )

        service = _make_service(db_session, partner_client)
        request = TransactionRequest(
            external_id=uuid.uuid4(), amount=Decimal("75.00"), kind=KindEnum.DEBIT
        )

        with pytest.raises(PartnerUnavailableError):
            await service.create_transaction(request)

        # Verify the transaction is in the DB with FAILED status
        from app.repositories.transaction_repository import TransactionRepository

        repo = TransactionRepository(db_session)
        saved = await repo.get_by_external_id(request.external_id)
        assert saved is not None
        assert saved.status == StatusEnum.FAILED

    async def test_partner_unavailable_does_not_publish(self, db_session, mock_publisher):
        """No RabbitMQ event should be published when the partner fails."""
        partner_client = AsyncMock()
        partner_client.send_transaction = AsyncMock(side_effect=PartnerUnavailableError())

        service = _make_service(db_session, partner_client)
        request = TransactionRequest(
            external_id=uuid.uuid4(), amount=Decimal("30.00"), kind=KindEnum.CREDIT
        )

        with pytest.raises(PartnerUnavailableError):
            await service.create_transaction(request)

        mock_publisher.assert_not_awaited()

    async def test_publisher_called_with_correct_payload(self, db_session, mock_publisher):
        """Publisher is called with the right transaction data."""
        partner_tx_id = str(uuid.uuid4())
        partner_client = AsyncMock()
        partner_client.send_transaction = AsyncMock(return_value={"transaction_id": partner_tx_id})

        service = _make_service(db_session, partner_client)
        ext_id = uuid.uuid4()
        request = TransactionRequest(
            external_id=ext_id, amount=Decimal("200.00"), kind=KindEnum.CREDIT
        )

        await service.create_transaction(request)

        call_kwargs = mock_publisher.call_args.kwargs
        assert call_kwargs["external_id"] == str(ext_id)
        assert call_kwargs["kind"] == KindEnum.CREDIT
        assert call_kwargs["status"] == StatusEnum.PROCESSED


class TestGetBalance:
    async def test_empty_balance(self, db_session):
        """Balance is zero when no processed transactions exist."""
        service = _make_service(db_session)
        balance = await service.get_balance()
        assert balance.total_credit == Decimal("0.00")
        assert balance.total_debit == Decimal("0.00")
        assert balance.balance == Decimal("0.00")

    async def test_balance_with_processed_transactions(self, db_session, mock_publisher):
        """Balance reflects only PROCESSED transactions."""
        partner_client = AsyncMock()
        partner_client.send_transaction = AsyncMock(
            return_value={"transaction_id": str(uuid.uuid4())}
        )
        service = _make_service(db_session, partner_client)

        await service.create_transaction(
            TransactionRequest(
                external_id=uuid.uuid4(), amount=Decimal("300.00"), kind=KindEnum.CREDIT
            )
        )
        await service.create_transaction(
            TransactionRequest(
                external_id=uuid.uuid4(), amount=Decimal("100.00"), kind=KindEnum.DEBIT
            )
        )

        balance = await service.get_balance()
        assert balance.total_credit == Decimal("300.00")
        assert balance.total_debit == Decimal("100.00")
        assert balance.balance == Decimal("200.00")
