import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from httpx import ASGITransport, AsyncClient

from app.api.deps.auth import require_auth
from app.core.config import get_settings
from app.main import app
from app.models import KindEnum

pytestmark = pytest.mark.asyncio

LOGIN_URL = "/api/v1/auth/login"
TRANSACTION_URL = "/api/v1/transaction"


class TestAuthLogin:
    async def test_login_returns_token(self):
        settings = get_settings()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                LOGIN_URL,
                json={
                    "username": settings.API_AUTH_USERNAME,
                    "password": settings.API_AUTH_PASSWORD,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == settings.API_AUTH_TOKEN_EXPIRE_SECONDS
        assert isinstance(data["access_token"], str)
        assert data["access_token"]

    async def test_login_with_invalid_credentials_returns_401(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                LOGIN_URL,
                json={"username": "wrong", "password": "wrong"},
            )

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid username or password"

    async def test_can_use_issued_token_on_protected_route(self, http_client, mock_publisher):
        with patch(
            "app.services.transaction_service.PartnerClient.send_transaction",
            new_callable=AsyncMock,
            return_value={"transaction_id": str(uuid.uuid4())},
        ):
            response = await http_client.post(
                TRANSACTION_URL,
                json={
                    "external_id": str(uuid.uuid4()),
                    "amount": "10.00",
                    "kind": KindEnum.CREDIT,
                },
            )

        assert response.status_code == 201

    async def test_protected_route_with_non_bearer_scheme_returns_401(self):
        payload = {
            "external_id": str(uuid.uuid4()),
            "amount": "10.00",
            "kind": KindEnum.CREDIT,
        }

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Basic abc123"},
        ) as client:
            response = await client.post(TRANSACTION_URL, json=payload)

        assert response.status_code == 401
        assert response.json()["detail"] == "Not authenticated"

    async def test_require_auth_allows_configured_static_token(self):
        settings = get_settings()
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=settings.API_AUTH_TOKEN,
        )

        result = await require_auth(credentials=credentials, settings=settings)

        assert result is None
