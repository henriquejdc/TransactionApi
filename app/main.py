from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.exceptions import PartnerUnavailableError, TransactionAlreadyProcessedError
from app.core.logging import get_logger, setup_logging
from app.db import session as _db_session
from app.models.transaction import Transaction  # noqa: F401 – registers model with Base

setup_logging()
logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up Transaction API (env=%s)…", settings.APP_ENV)
    yield
    logger.info("Shutting down Transaction API…")
    await _db_session.engine.dispose()


app = FastAPI(
    title="Transaction API",
    description=(
        "Async transaction processing API with idempotency, "
        "bank-partner integration and RabbitMQ event publishing."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.include_router(api_router)


@app.exception_handler(TransactionAlreadyProcessedError)
async def duplicate_transaction_handler(
    request: Request, exc: TransactionAlreadyProcessedError
) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": exc.message})


@app.exception_handler(PartnerUnavailableError)
async def partner_unavailable_handler(
    request: Request, exc: PartnerUnavailableError
) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": exc.message})


@app.get("/health", tags=["Health"], summary="Health check")
async def health() -> dict:
    return {"status": "ok"}
