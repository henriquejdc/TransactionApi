import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models import KindEnum, StatusEnum

pytestmark = pytest.mark.asyncio

TRANSACTION_URL = "/api/v1/transaction"
BALANCE_URL = "/api/v1/transaction/balance"


class TestCreateTransactionEndpoint:
    async def test_requires_authentication(self):
        payload = {
            "external_id": str(uuid.uuid4()),
            "amount": "10.00",
            "kind": KindEnum.CREDIT,
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(TRANSACTION_URL, json=payload)

        assert response.status_code == 401
        assert response.json()["detail"] == "Not authenticated"

    async def test_rejects_invalid_token(self):
        payload = {
            "external_id": str(uuid.uuid4()),
            "amount": "10.00",
            "kind": KindEnum.CREDIT,
        }

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer invalid-token"},
        ) as client:
            response = await client.post(TRANSACTION_URL, json=payload)

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid authentication credentials"

    async def test_create_credit_returns_201(self, http_client, mock_publisher):
        partner_tx_id = str(uuid.uuid4())
        with patch(
            "app.services.transaction_service.PartnerClient.send_transaction",
            new_callable=AsyncMock,
            return_value={"transaction_id": partner_tx_id, "status": "approved"},
        ):
            payload = {
                "external_id": str(uuid.uuid4()),
                "amount": "150.75",
                "kind": KindEnum.CREDIT,
            }
            response = await http_client.post(TRANSACTION_URL, json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == StatusEnum.PROCESSED
        assert data["kind"] == KindEnum.CREDIT
        assert data["partner_transaction_id"] == partner_tx_id

    async def test_create_debit_returns_201(self, http_client, mock_publisher):
        with patch(
            "app.services.transaction_service.PartnerClient.send_transaction",
            new_callable=AsyncMock,
            return_value={"transaction_id": str(uuid.uuid4())},
        ):
            payload = {
                "external_id": str(uuid.uuid4()),
                "amount": "50.00",
                "kind": KindEnum.DEBIT,
            }
            response = await http_client.post(TRANSACTION_URL, json=payload)

        assert response.status_code == 201
        assert response.json()["kind"] == KindEnum.DEBIT

    async def test_duplicate_external_id_returns_409(self, http_client, mock_publisher):
        ext_id = str(uuid.uuid4())
        with patch(
            "app.services.transaction_service.PartnerClient.send_transaction",
            new_callable=AsyncMock,
            return_value={"transaction_id": str(uuid.uuid4())},
        ):
            payload = {"external_id": ext_id, "amount": "10.00", "kind": KindEnum.CREDIT}
            await http_client.post(TRANSACTION_URL, json=payload)
            response = await http_client.post(TRANSACTION_URL, json=payload)

        assert response.status_code == 409
        assert ext_id in response.json()["detail"]

    async def test_partner_unavailable_returns_503(self, http_client, mock_publisher):
        from app.core.exceptions import PartnerUnavailableError

        with patch(
            "app.services.transaction_service.PartnerClient.send_transaction",
            new_callable=AsyncMock,
            side_effect=PartnerUnavailableError("Partner is down"),
        ):
            payload = {
                "external_id": str(uuid.uuid4()),
                "amount": "99.00",
                "kind": KindEnum.DEBIT,
            }
            response = await http_client.post(TRANSACTION_URL, json=payload)

        assert response.status_code == 503
        assert "Partner" in response.json()["detail"]

    async def test_invalid_amount_zero_returns_422(self, http_client):
        payload = {"external_id": str(uuid.uuid4()), "amount": "0", "kind": KindEnum.CREDIT}
        response = await http_client.post(TRANSACTION_URL, json=payload)
        assert response.status_code == 422

    async def test_invalid_amount_negative_returns_422(self, http_client):
        payload = {
            "external_id": str(uuid.uuid4()),
            "amount": "-10.00",
            "kind": KindEnum.CREDIT,
        }
        response = await http_client.post(TRANSACTION_URL, json=payload)
        assert response.status_code == 422

    async def test_invalid_kind_returns_422(self, http_client):
        payload = {
            "external_id": str(uuid.uuid4()),
            "amount": "10.00",
            "kind": "invalid_kind",
        }
        response = await http_client.post(TRANSACTION_URL, json=payload)
        assert response.status_code == 422

    async def test_missing_external_id_returns_422(self, http_client):
        payload = {"amount": "10.00", "kind": KindEnum.CREDIT}
        response = await http_client.post(TRANSACTION_URL, json=payload)
        assert response.status_code == 422

    async def test_invalid_uuid_returns_422(self, http_client):
        payload = {"external_id": "not-a-uuid", "amount": "10.00", "kind": KindEnum.CREDIT}
        response = await http_client.post(TRANSACTION_URL, json=payload)
        assert response.status_code == 422

    async def test_response_schema_fields(self, http_client, mock_publisher):
        """Verify the response contains all required fields."""
        with patch(
            "app.services.transaction_service.PartnerClient.send_transaction",
            new_callable=AsyncMock,
            return_value={"transaction_id": str(uuid.uuid4())},
        ):
            payload = {
                "external_id": str(uuid.uuid4()),
                "amount": "500.00",
                "kind": KindEnum.CREDIT,
            }
            response = await http_client.post(TRANSACTION_URL, json=payload)

        assert response.status_code == 201
        data = response.json()
        for field in ("id", "external_id", "amount", "kind", "status", "created_at", "updated_at"):
            assert field in data, f"Missing field: {field}"


class TestGetBalanceEndpoint:
    async def test_balance_empty(self, http_client):
        response = await http_client.get(BALANCE_URL)
        assert response.status_code == 200
        data = response.json()
        assert Decimal(data["total_credit"]) == Decimal("0")
        assert Decimal(data["total_debit"]) == Decimal("0")
        assert Decimal(data["balance"]) == Decimal("0")

    async def test_balance_after_transactions(self, http_client, mock_publisher):
        with patch(
            "app.services.transaction_service.PartnerClient.send_transaction",
            new_callable=AsyncMock,
            return_value={"transaction_id": str(uuid.uuid4())},
        ):
            await http_client.post(
                TRANSACTION_URL,
                json={
                    "external_id": str(uuid.uuid4()),
                    "amount": "400.00",
                    "kind": KindEnum.CREDIT,
                },
            )
            await http_client.post(
                TRANSACTION_URL,
                json={"external_id": str(uuid.uuid4()), "amount": "150.00", "kind": KindEnum.DEBIT},
            )

        response = await http_client.get(BALANCE_URL)
        assert response.status_code == 200
        data = response.json()
        assert Decimal(data["total_credit"]) == Decimal("400.00")
        assert Decimal(data["total_debit"]) == Decimal("150.00")
        assert Decimal(data["balance"]) == Decimal("250.00")


class TestHealthEndpoint:
    async def test_health_ok(self, http_client):
        response = await http_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
