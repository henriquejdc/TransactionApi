import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.core.config import Settings


class AuthService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def authenticate(self, username: str, password: str) -> bool:
        return hmac.compare_digest(
            username, self.settings.API_AUTH_USERNAME
        ) and hmac.compare_digest(password, self.settings.API_AUTH_PASSWORD)

    def issue_token(self, subject: str) -> str:
        payload = {
            "sub": subject,
            "exp": int(time.time()) + self.settings.API_AUTH_TOKEN_EXPIRE_SECONDS,
        }
        payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("utf-8").rstrip("=")
        signature = self._sign(payload_b64)
        return f"{payload_b64}.{signature}"

    def verify_token(self, token: str) -> dict[str, Any] | None:
        try:
            payload_b64, signature = token.split(".", 1)
        except ValueError:
            return None

        expected_signature = self._sign(payload_b64)
        if not hmac.compare_digest(signature, expected_signature):
            return None

        payload = self._decode_payload(payload_b64)
        if payload is None:
            return None

        expires_at = payload.get("exp")
        subject = payload.get("sub")
        if not isinstance(expires_at, int) or expires_at < int(time.time()):
            return None
        if not isinstance(subject, str) or not subject:
            return None

        return payload

    def _sign(self, payload_b64: str) -> str:
        digest = hmac.new(
            self.settings.SECRET_KEY.encode("utf-8"),
            payload_b64.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")

    @staticmethod
    def _decode_payload(payload_b64: str) -> dict[str, Any] | None:
        padding = "=" * (-len(payload_b64) % 4)
        try:
            payload_bytes = base64.urlsafe_b64decode(f"{payload_b64}{padding}")
            payload = json.loads(payload_bytes.decode("utf-8"))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return None

        return payload if isinstance(payload, dict) else None
