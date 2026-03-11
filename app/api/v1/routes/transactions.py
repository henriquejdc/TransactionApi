from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import PartnerUnavailableError, TransactionAlreadyProcessedError
from app.core.logging import get_logger
from app.db.session import get_db
from app.schemas.transaction import BalanceResponse, TransactionRequest, TransactionResponse
from app.services.partner_client import PartnerClient
from app.services.transaction_service import TransactionService

logger = get_logger(__name__)

router = APIRouter(prefix="/transaction", tags=["Transactions"])


def get_transaction_service(session: AsyncSession = Depends(get_db)) -> TransactionService:
    return TransactionService(session=session, partner_client=PartnerClient())


@router.post(
    "",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new transaction",
    description=(
        "Receives a transaction request, checks idempotency, calls the bank partner, "
        "persists the result and asynchronously publishes an event to RabbitMQ."
    ),
)
async def create_transaction(
    request: TransactionRequest,
    service: TransactionService = Depends(get_transaction_service),
) -> TransactionResponse:
    logger.info("POST /transaction | external_id=%s", request.external_id)
    try:
        return await service.create_transaction(request)
    except TransactionAlreadyProcessedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.message,
        ) from exc
    except PartnerUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.message,
        ) from exc


@router.get(
    "/balance",
    response_model=BalanceResponse,
    status_code=status.HTTP_200_OK,
    summary="Get account balance",
    description="Returns the aggregated credit, debit and net balance from all processed transactions.",
)
async def get_balance(
    service: TransactionService = Depends(get_transaction_service),
) -> BalanceResponse:
    logger.info("GET /transaction/balance")
    return await service.get_balance()
