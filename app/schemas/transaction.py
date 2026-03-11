import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.transaction import KindEnum, StatusEnum


class TransactionRequest(BaseModel):
    """Incoming payload for creating a new transaction."""

    external_id: uuid.UUID = Field(..., description="Unique identifier provided by the client.")
    amount: Decimal = Field(..., gt=0, description="Transaction amount. Must be greater than zero.")
    kind: KindEnum = Field(..., description="Transaction type: 'credit' or 'debit'.")

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        if v <= 0:  # pragma: no cover
            raise ValueError("Amount must be a positive number.")
        return round(v, 2)


class TransactionResponse(BaseModel):
    """Outgoing payload returned after processing a transaction."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    external_id: uuid.UUID
    amount: Decimal
    kind: KindEnum
    status: StatusEnum
    partner_transaction_id: Optional[str] = None
    partner_response: Optional[Any] = None
    created_at: datetime
    updated_at: datetime


class BalanceResponse(BaseModel):
    """Response payload for balance queries."""

    total_credit: Decimal = Field(default=Decimal("0.00"))
    total_debit: Decimal = Field(default=Decimal("0.00"))
    balance: Decimal = Field(default=Decimal("0.00"))
