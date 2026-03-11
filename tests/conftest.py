import uuid
from decimal import Decimal
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.session import Base, get_db
from app.main import app
from app.models.transaction import KindEnum, StatusEnum, Transaction

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables():
    """Create all tables once per test session."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional test DB session that rolls back after each test."""
    async with test_engine.connect() as conn:
        await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()


@pytest.fixture()
def mock_publisher():
    """Mock the RabbitMQ publisher so tests never touch RabbitMQ."""
    with patch(
        "app.services.transaction_service.publish_transaction_event",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


@pytest.fixture()
def mock_partner_ok():
    """Mock a successful partner response."""
    partner_tx_id = str(uuid.uuid4())
    with patch(
        "app.services.transaction_service.PartnerClient.send_transaction",
        new_callable=AsyncMock,
        return_value={"transaction_id": partner_tx_id, "status": "approved"},
    ) as mock:
        yield mock, partner_tx_id


@pytest.fixture()
def valid_transaction_payload() -> dict:
    return {
        "external_id": str(uuid.uuid4()),
        "amount": "100.50",
        "kind": KindEnum.CREDIT,
    }


@pytest.fixture()
def sample_transaction(db_session: AsyncSession) -> Transaction:
    """A pre-built (unsaved) Transaction ORM object."""
    return Transaction(
        id=uuid.uuid4(),
        external_id=uuid.uuid4(),
        amount=Decimal("250.00"),
        kind=KindEnum.CREDIT,
        status=StatusEnum.PENDING,
    )


@pytest.fixture()
def auth_credentials() -> dict[str, str]:
    settings = get_settings()
    return {
        "username": settings.API_AUTH_USERNAME,
        "password": settings.API_AUTH_PASSWORD,
    }


@pytest_asyncio.fixture()
async def auth_headers(auth_credentials: dict[str, str]) -> dict[str, str]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/auth/login", json=auth_credentials)

    assert response.status_code == 200
    access_token = response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


@pytest_asyncio.fixture()
async def http_client(
    db_session: AsyncSession, auth_headers: dict[str, str]
) -> AsyncGenerator[AsyncClient, None]:
    """HTTP test client with the DB dependency overridden to use the test session."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers=auth_headers,
    ) as client:
        yield client

    app.dependency_overrides.clear()
