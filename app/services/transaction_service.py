import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import PartnerUnavailableError, TransactionAlreadyProcessedError
from app.core.logging import get_logger
from app.models.transaction import StatusEnum
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.transaction import BalanceResponse, TransactionRequest, TransactionResponse
from app.services.partner_client import PartnerClient
from app.workers.publisher import publish_transaction_event

logger = get_logger(__name__)


class TransactionService:
    """
    Orchestrates the full transaction lifecycle:

    1. Idempotency check (by external_id)
    2. Persist with PENDING status
    3. Call the bank partner synchronously
    4. Update status to PROCESSED or FAILED
    5. Fire-and-forget publish to RabbitMQ
    """

    def __init__(
        self,
        session: AsyncSession,
        partner_client: PartnerClient | None = None,
    ) -> None:
        self._repo = TransactionRepository(session)
        self._partner = partner_client or PartnerClient()

    async def create_transaction(self, request: TransactionRequest) -> TransactionResponse:
        logger.info(
            "Processing transaction | external_id=%s kind=%s amount=%s",
            request.external_id,
            request.kind,
            request.amount,
        )

        existing = await self._repo.get_by_external_id(request.external_id)
        if existing is not None:
            logger.warning(
                "Duplicate transaction request | external_id=%s status=%s",
                request.external_id,
                existing.status,
            )
            raise TransactionAlreadyProcessedError(str(request.external_id))

        transaction = await self._repo.create(
            external_id=request.external_id,
            amount=request.amount,
            kind=request.kind,
        )

        try:
            partner_data = await self._partner.send_transaction(
                external_id=request.external_id,
                amount=float(request.amount),
                kind=request.kind.value,
            )
            partner_transaction_id = partner_data.get("transaction_id")

            transaction = await self._repo.update_status(
                transaction=transaction,
                status=StatusEnum.PROCESSED,
                partner_transaction_id=partner_transaction_id,
                partner_response=partner_data,
            )
            logger.info(
                "Transaction processed successfully | id=%s partner_id=%s",
                transaction.id,
                partner_transaction_id,
            )

        except PartnerUnavailableError as exc:
            transaction = await self._repo.update_status(
                transaction=transaction,
                status=StatusEnum.FAILED,
                partner_response={"error": exc.message},
            )
            logger.error(
                "Transaction failed due to partner unavailability | id=%s error=%s",
                transaction.id,
                exc.message,
            )
            raise

        await publish_transaction_event(
            transaction_id=str(transaction.id),
            external_id=str(transaction.external_id),
            kind=transaction.kind.value,
            status=transaction.status.value,
            amount=float(transaction.amount),
        )

        return TransactionResponse.model_validate(transaction)

    async def get_balance(self) -> BalanceResponse:
        """Return aggregated credit/debit balance from processed transactions."""
        logger.info("Fetching account balance")
        data = await self._repo.get_balance()
        return BalanceResponse(**data)
