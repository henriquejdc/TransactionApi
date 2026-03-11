class PartnerUnavailableError(Exception):
    """Raised when the bank partner API is unavailable or returns an error."""

    def __init__(self, message: str = "Bank partner is currently unavailable."):
        self.message = message
        super().__init__(self.message)


class TransactionAlreadyProcessedError(Exception):
    """Raised when attempting to process a transaction with a duplicate external_id."""

    def __init__(self, external_id: str):
        self.message = f"Transaction with external_id '{external_id}' already exists."
        super().__init__(self.message)


class TransactionNotFoundError(Exception):
    """Raised when a requested transaction is not found."""

    def __init__(self, external_id: str):
        self.message = f"Transaction with external_id '{external_id}' not found."
        super().__init__(self.message)
