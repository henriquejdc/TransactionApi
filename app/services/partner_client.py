import uuid
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.exceptions import PartnerUnavailableError
from app.core.logging import get_logger

logger = get_logger(__name__)


class PartnerClient:
    """HTTP client for communicating with the external bank partner API."""

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.PARTNER_API_URL
        self._timeout = settings.PARTNER_API_TIMEOUT

    async def send_transaction(
        self,
        external_id: uuid.UUID,
        amount: float,
        kind: str,
    ) -> dict[str, Any]:
        """
        Submit a transaction to the partner bank and return its response.

        Raises:
            PartnerUnavailableError: on connection errors, timeouts, or 5xx responses.
        """
        payload = {
            "external_id": str(external_id),
            "amount": amount,
            "kind": kind,
        }
        logger.info(
            "Sending transaction to partner | external_id=%s kind=%s amount=%s",
            external_id,
            kind,
            amount,
        )
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
                response = await client.post("/authorize", json=payload)

            if response.status_code >= 500:
                raise PartnerUnavailableError(f"Partner returned HTTP {response.status_code}.")

            response.raise_for_status()
            data = response.json()
            logger.info(
                "Partner responded | external_id=%s partner_id=%s",
                external_id,
                data.get("transaction_id"),
            )
            return data

        except httpx.TimeoutException as exc:
            logger.error("Partner request timed out | external_id=%s", external_id)
            raise PartnerUnavailableError("Partner request timed out.") from exc

        except httpx.ConnectError as exc:
            logger.error("Could not connect to partner | external_id=%s", external_id)
            raise PartnerUnavailableError("Could not connect to partner.") from exc

        except PartnerUnavailableError:
            raise

        except httpx.HTTPStatusError as exc:
            logger.error(
                "Partner returned error | external_id=%s status=%s",
                external_id,
                exc.response.status_code,
            )
            raise PartnerUnavailableError(
                f"Partner returned HTTP {exc.response.status_code}."
            ) from exc
