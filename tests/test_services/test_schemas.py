import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models import KindEnum
from app.schemas.transaction import BalanceResponse, TransactionRequest


class TestTransactionRequest:
    def test_valid_credit(self):
        req = TransactionRequest(
            external_id=uuid.uuid4(), amount=Decimal("99.99"), kind=KindEnum.CREDIT
        )
        assert req.kind.value == KindEnum.CREDIT

    def test_valid_debit(self):
        req = TransactionRequest(
            external_id=uuid.uuid4(), amount=Decimal("1.00"), kind=KindEnum.DEBIT
        )
        assert req.kind.value == KindEnum.DEBIT

    def test_zero_amount_raises(self):
        with pytest.raises(ValidationError):
            TransactionRequest(external_id=uuid.uuid4(), amount=Decimal("0"), kind=KindEnum.CREDIT)

    def test_negative_amount_raises(self):
        with pytest.raises(ValidationError):
            TransactionRequest(
                external_id=uuid.uuid4(), amount=Decimal("-5.00"), kind=KindEnum.DEBIT
            )

    def test_amount_is_rounded_to_2_decimals(self):
        req = TransactionRequest(
            external_id=uuid.uuid4(), amount=Decimal("10.999"), kind=KindEnum.CREDIT
        )
        assert req.amount == Decimal("11.00")

    def test_invalid_kind_raises(self):
        with pytest.raises(ValidationError):
            TransactionRequest(
                external_id=uuid.uuid4(), amount=Decimal("10.00"), kind="transition"  # type: ignore
            )

    def test_invalid_uuid_raises(self):
        with pytest.raises(ValidationError):
            TransactionRequest(
                external_id="not-a-uuid", amount=Decimal("10.00"), kind=KindEnum.CREDIT  # type: ignore
            )


class TestBalanceResponse:
    def test_defaults_are_zero(self):
        bal = BalanceResponse()
        assert bal.total_credit == Decimal("0.00")
        assert bal.total_debit == Decimal("0.00")
        assert bal.balance == Decimal("0.00")
