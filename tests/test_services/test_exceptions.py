from app.core.exceptions import (
    PartnerUnavailableError,
    TransactionAlreadyProcessedError,
    TransactionNotFoundError,
)


class TestPartnerUnavailableError:
    def test_default_message(self):
        exc = PartnerUnavailableError()
        assert "unavailable" in exc.message.lower()

    def test_custom_message(self):
        exc = PartnerUnavailableError("custom error")
        assert exc.message == "custom error"

    def test_is_exception(self):
        assert isinstance(PartnerUnavailableError(), Exception)


class TestTransactionAlreadyProcessedError:
    def test_message_contains_external_id(self):
        ext_id = "abc-123"
        exc = TransactionAlreadyProcessedError(ext_id)
        assert ext_id in exc.message

    def test_is_exception(self):
        assert isinstance(TransactionAlreadyProcessedError("id"), Exception)


class TestTransactionNotFoundError:
    def test_message_contains_external_id(self):
        ext_id = "xyz-456"
        exc = TransactionNotFoundError(ext_id)
        assert ext_id in exc.message

    def test_is_exception(self):
        assert isinstance(TransactionNotFoundError("id"), Exception)
