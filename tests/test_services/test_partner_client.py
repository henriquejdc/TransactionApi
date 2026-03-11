import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.exceptions import PartnerUnavailableError
from app.models import KindEnum
from app.services.partner_client import PartnerClient

pytestmark = pytest.mark.asyncio


class TestPartnerClient:
    async def test_send_transaction_success(self):
        """A 200 response with a transaction_id is returned as a dict."""
        partner_id = str(uuid.uuid4())
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "transaction_id": partner_id,
            "status": "approved",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.partner_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            client = PartnerClient()
            result = await client.send_transaction(
                external_id=uuid.uuid4(), amount=100.0, kind=KindEnum.CREDIT
            )

        assert result["transaction_id"] == partner_id

    async def test_send_transaction_500_raises_partner_unavailable(self):
        """HTTP 5xx from partner raises PartnerUnavailableError."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("app.services.partner_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            client = PartnerClient()
            with pytest.raises(PartnerUnavailableError) as exc_info:
                await client.send_transaction(
                    external_id=uuid.uuid4(), amount=50.0, kind=KindEnum.DEBIT
                )

        assert "503" in exc_info.value.message or "500" in exc_info.value.message

    async def test_send_transaction_timeout_raises_partner_unavailable(self):
        """Timeout raises PartnerUnavailableError."""
        with patch("app.services.partner_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            client = PartnerClient()
            with pytest.raises(PartnerUnavailableError) as exc_info:
                await client.send_transaction(
                    external_id=uuid.uuid4(), amount=10.0, kind=KindEnum.CREDIT
                )

        assert "timed out" in exc_info.value.message.lower()

    async def test_send_transaction_connect_error_raises_partner_unavailable(self):
        """Connection error raises PartnerUnavailableError."""
        with patch("app.services.partner_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            client = PartnerClient()
            with pytest.raises(PartnerUnavailableError) as exc_info:
                await client.send_transaction(
                    external_id=uuid.uuid4(), amount=10.0, kind=KindEnum.DEBIT
                )

        assert "connect" in exc_info.value.message.lower()

    async def test_send_transaction_4xx_raises_partner_unavailable(self):
        """HTTP 4xx raises PartnerUnavailableError via raise_for_status."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_request = MagicMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "400 Bad Request", request=mock_request, response=mock_response
            )
        )

        with patch("app.services.partner_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            client = PartnerClient()
            with pytest.raises(PartnerUnavailableError) as exc_info:
                await client.send_transaction(
                    external_id=uuid.uuid4(), amount=10.0, kind=KindEnum.CREDIT
                )

        assert "400" in exc_info.value.message
