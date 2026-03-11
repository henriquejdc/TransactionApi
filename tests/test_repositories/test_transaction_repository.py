import uuid
from decimal import Decimal

import pytest

from app.models.transaction import KindEnum, StatusEnum
from app.repositories.transaction_repository import TransactionRepository

pytestmark = pytest.mark.asyncio


class TestTransactionRepository:
    async def test_create_returns_pending_transaction(self, db_session):
        repo = TransactionRepository(db_session)
        ext_id = uuid.uuid4()

        tx = await repo.create(
            external_id=ext_id,
            amount=Decimal("100.00"),
            kind=KindEnum.CREDIT,
        )

        assert tx.id is not None
        assert tx.external_id == ext_id
        assert tx.amount == Decimal("100.00")
        assert tx.kind == KindEnum.CREDIT
        assert tx.status == StatusEnum.PENDING

    async def test_get_by_external_id_found(self, db_session):
        repo = TransactionRepository(db_session)
        ext_id = uuid.uuid4()
        created = await repo.create(
            external_id=ext_id, amount=Decimal("50.00"), kind=KindEnum.DEBIT
        )

        found = await repo.get_by_external_id(ext_id)

        assert found is not None
        assert found.id == created.id

    async def test_get_by_external_id_not_found(self, db_session):
        repo = TransactionRepository(db_session)
        result = await repo.get_by_external_id(uuid.uuid4())
        assert result is None

    async def test_get_by_id_found(self, db_session):
        repo = TransactionRepository(db_session)
        tx = await repo.create(
            external_id=uuid.uuid4(), amount=Decimal("25.00"), kind=KindEnum.CREDIT
        )

        found = await repo.get_by_id(tx.id)
        assert found is not None
        assert found.external_id == tx.external_id

    async def test_get_by_id_not_found(self, db_session):
        repo = TransactionRepository(db_session)
        result = await repo.get_by_id(uuid.uuid4())
        assert result is None

    async def test_update_status_to_processed(self, db_session):
        repo = TransactionRepository(db_session)
        tx = await repo.create(
            external_id=uuid.uuid4(), amount=Decimal("200.00"), kind=KindEnum.CREDIT
        )
        partner_id = str(uuid.uuid4())

        updated = await repo.update_status(
            transaction=tx,
            status=StatusEnum.PROCESSED,
            partner_transaction_id=partner_id,
            partner_response={"transaction_id": partner_id, "status": "approved"},
        )

        assert updated.status == StatusEnum.PROCESSED
        assert updated.partner_transaction_id == partner_id
        assert updated.partner_response["status"] == "approved"

    async def test_update_status_to_failed(self, db_session):
        repo = TransactionRepository(db_session)
        tx = await repo.create(
            external_id=uuid.uuid4(), amount=Decimal("99.99"), kind=KindEnum.DEBIT
        )

        updated = await repo.update_status(
            transaction=tx,
            status=StatusEnum.FAILED,
            partner_response={"error": "timeout"},
        )

        assert updated.status == StatusEnum.FAILED
        assert updated.partner_response["error"] == "timeout"

    async def test_get_balance_empty(self, db_session):
        repo = TransactionRepository(db_session)
        result = await repo.get_balance()
        assert result["total_credit"] == Decimal("0")
        assert result["total_debit"] == Decimal("0")
        assert result["balance"] == Decimal("0")

    async def test_get_balance_only_processed(self, db_session):
        """PENDING/FAILED transactions must not affect balance."""
        repo = TransactionRepository(db_session)
        partner_id = str(uuid.uuid4())

        credit_tx = await repo.create(
            external_id=uuid.uuid4(), amount=Decimal("500.00"), kind=KindEnum.CREDIT
        )
        await repo.update_status(credit_tx, StatusEnum.PROCESSED, partner_transaction_id=partner_id)

        debit_tx = await repo.create(
            external_id=uuid.uuid4(), amount=Decimal("200.00"), kind=KindEnum.DEBIT
        )
        await repo.update_status(debit_tx, StatusEnum.PROCESSED, partner_transaction_id=partner_id)

        # This PENDING one should be excluded
        await repo.create(external_id=uuid.uuid4(), amount=Decimal("9999.00"), kind=KindEnum.CREDIT)

        result = await repo.get_balance()
        assert result["total_credit"] == Decimal("500.00")
        assert result["total_debit"] == Decimal("200.00")
        assert result["balance"] == Decimal("300.00")
