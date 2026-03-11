import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.exceptions import PartnerUnavailableError, TransactionAlreadyProcessedError
from app.main import app, duplicate_transaction_handler, partner_unavailable_handler
from app.models import KindEnum

pytestmark = pytest.mark.asyncio


async def get_auth_headers() -> dict[str, str]:
    settings = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "username": settings.API_AUTH_USERNAME,
                "password": settings.API_AUTH_PASSWORD,
            },
        )

    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


class TestLifespan:
    async def test_lifespan_startup_and_shutdown(self):
        """App starts and shuts down cleanly (exercises the full lifespan context)."""
        from fastapi import FastAPI

        import app.db.session as db_session_module
        from app.main import lifespan

        original_engine = db_session_module.engine
        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
        db_session_module.engine = mock_engine

        test_app = FastAPI(lifespan=lifespan)

        @test_app.get("/ping")
        async def ping():
            return {"ok": True}

        try:
            async with test_app.router.lifespan_context(test_app):
                async with AsyncClient(
                    transport=ASGITransport(app=test_app), base_url="http://test"
                ) as client:
                    response = await client.get("/ping")
        finally:
            db_session_module.engine = original_engine

        assert response.status_code == 200
        mock_engine.dispose.assert_awaited_once()


class TestGlobalExceptionHandlers:
    async def test_duplicate_transaction_handler_directly(self):
        """Calling the handler function directly covers the return statement."""
        ext_id = str(uuid.uuid4())
        exc = TransactionAlreadyProcessedError(ext_id)
        request = MagicMock()

        response = await duplicate_transaction_handler(request, exc)

        assert response.status_code == 409
        import json

        body = json.loads(response.body)
        assert ext_id in body["detail"]

    async def test_partner_unavailable_handler_directly(self):
        """Calling the handler function directly covers the return statement."""
        exc = PartnerUnavailableError("Partner is down")
        request = MagicMock()

        response = await partner_unavailable_handler(request, exc)

        assert response.status_code == 503
        import json

        body = json.loads(response.body)
        assert "Partner is down" in body["detail"]

    async def test_duplicate_handler_via_http(self):
        """TransactionAlreadyProcessedError bubbles up → 409."""
        from app.db.session import get_db
        from app.services.transaction_service import TransactionService

        ext_id = uuid.uuid4()

        async def override_get_db():
            yield None

        async def mock_create(*args, **kwargs):
            raise TransactionAlreadyProcessedError(str(ext_id))

        with patch.object(TransactionService, "create_transaction", new=mock_create):
            app.dependency_overrides[get_db] = override_get_db
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers=await get_auth_headers(),
            ) as client:
                response = await client.post(
                    "/api/v1/transaction",
                    json={"external_id": str(ext_id), "amount": "10.00", "kind": KindEnum.CREDIT},
                )
            app.dependency_overrides.clear()

        assert response.status_code == 409

    async def test_partner_unavailable_via_http(self):
        """PartnerUnavailableError bubbles up → 503."""
        from app.db.session import get_db
        from app.services.transaction_service import TransactionService

        async def override_get_db():
            yield None

        async def mock_create(*args, **kwargs):
            raise PartnerUnavailableError("down")

        with patch.object(TransactionService, "create_transaction", new=mock_create):
            app.dependency_overrides[get_db] = override_get_db
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers=await get_auth_headers(),
            ) as client:
                response = await client.post(
                    "/api/v1/transaction",
                    json={
                        "external_id": str(uuid.uuid4()),
                        "amount": "10.00",
                        "kind": KindEnum.CREDIT,
                    },
                )
            app.dependency_overrides.clear()

        assert response.status_code == 503
