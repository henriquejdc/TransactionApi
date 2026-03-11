import uuid
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.transaction import KindEnum, StatusEnum, Transaction

logger = get_logger(__name__)


class TransactionRepository:
    """Data-access layer for Transaction entities."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_external_id(self, external_id: uuid.UUID) -> Optional[Transaction]:
        """Retrieve a transaction by its external_id (used for idempotency checks)."""
        result = await self._session.execute(
            select(Transaction).where(Transaction.external_id == external_id)
        )
        return result.scalars().first()

    async def get_by_id(self, transaction_id: uuid.UUID) -> Optional[Transaction]:
        """Retrieve a transaction by its internal UUID primary key."""
        result = await self._session.execute(
            select(Transaction).where(Transaction.id == transaction_id)
        )
        return result.scalars().first()

    async def create(
        self,
        external_id: uuid.UUID,
        amount: Decimal,
        kind: KindEnum,
    ) -> Transaction:
        """Persist a new Transaction record with PENDING status."""
        transaction = Transaction(
            external_id=external_id,
            amount=amount,
            kind=kind,
            status=StatusEnum.PENDING,
        )
        self._session.add(transaction)
        await self._session.flush()
        await self._session.refresh(transaction)
        logger.info(
            "Transaction created in DB | id=%s external_id=%s kind=%s amount=%s",
            transaction.id,
            transaction.external_id,
            transaction.kind,
            transaction.amount,
        )
        return transaction

    async def update_status(
        self,
        transaction: Transaction,
        status: StatusEnum,
        partner_transaction_id: Optional[str] = None,
        partner_response: Optional[Any] = None,
    ) -> Transaction:
        """Update the status and partner response of an existing transaction."""
        transaction.status = status
        if partner_transaction_id is not None:
            transaction.partner_transaction_id = partner_transaction_id
        if partner_response is not None:
            transaction.partner_response = partner_response
        self._session.add(transaction)
        await self._session.flush()
        await self._session.refresh(transaction)
        logger.info(
            "Transaction status updated | id=%s status=%s",
            transaction.id,
            transaction.status,
        )
        return transaction

    async def get_balance(self) -> dict:
        """Aggregate credit/debit totals for the balance endpoint."""
        result = await self._session.execute(
            select(
                Transaction.kind,
                func.coalesce(func.sum(Transaction.amount), 0).label("total"),
            )
            .where(Transaction.status == StatusEnum.PROCESSED.value)
            .group_by(Transaction.kind)
        )
        rows = result.all()
        totals = {row.kind: Decimal(str(row.total)) for row in rows}
        total_credit = totals.get(KindEnum.CREDIT, Decimal("0.00"))
        total_debit = totals.get(KindEnum.DEBIT, Decimal("0.00"))
        return {
            "total_credit": total_credit,
            "total_debit": total_debit,
            "balance": total_credit - total_debit,
        }
