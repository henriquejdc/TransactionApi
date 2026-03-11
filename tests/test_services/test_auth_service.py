import base64
import json
import time

import pytest

from app.core.config import Settings
from app.services.auth_service import AuthService


@pytest.fixture()
def auth_service() -> AuthService:
    settings = Settings(
        SECRET_KEY="test-secret",
        API_AUTH_USERNAME="admin",
        API_AUTH_PASSWORD="admin",
        API_AUTH_TOKEN_EXPIRE_SECONDS=3600,
        API_AUTH_TOKEN="dev-token",
    )
    return AuthService(settings=settings)


class TestAuthService:
    def test_verify_token_returns_none_when_token_has_no_separator(self, auth_service: AuthService):
        assert auth_service.verify_token("invalid-token-without-dot") is None

    def test_verify_token_returns_none_when_signature_is_invalid(self, auth_service: AuthService):
        token = auth_service.issue_token("admin")
        payload_b64, _signature = token.split(".", 1)

        assert auth_service.verify_token(f"{payload_b64}.invalid-signature") is None

    @pytest.mark.parametrize(
        ("payload", "expected"),
        [
            ({"sub": "", "exp": int(time.time()) + 60}, None),
            ({"sub": "admin", "exp": "not-an-int"}, None),
            ({"sub": "admin", "exp": int(time.time()) - 1}, None),
        ],
    )
    def test_verify_token_returns_none_for_invalid_claims(
        self, auth_service: AuthService, payload: dict, expected
    ):
        payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("utf-8").rstrip("=")
        signature = auth_service._sign(payload_b64)

        assert auth_service.verify_token(f"{payload_b64}.{signature}") is expected

    def test_verify_token_returns_none_when_payload_is_not_json_dict(
        self, auth_service: AuthService
    ):
        payload_b64 = base64.urlsafe_b64encode(json.dumps(["not", "a", "dict"]).encode("utf-8"))
        payload_b64 = payload_b64.decode("utf-8").rstrip("=")
        signature = auth_service._sign(payload_b64)

        assert auth_service.verify_token(f"{payload_b64}.{signature}") is None

    def test_decode_payload_returns_none_for_invalid_base64(self):
        assert AuthService._decode_payload("!!!") is None
