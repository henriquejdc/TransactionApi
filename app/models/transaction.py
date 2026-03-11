import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Enum, Numeric, String, types
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.db.session import Base


class UUIDType(types.TypeDecorator):
    impl = types.String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(types.String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        import uuid as _uuid

        if isinstance(value, _uuid.UUID):
            return value
        return _uuid.UUID(value)


class KindEnum(str, enum.Enum):
    CREDIT = "credit"
    DEBIT = "debit"


class StatusEnum(str, enum.Enum):
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUIDType, primary_key=True, default=uuid.uuid4, index=True)
    external_id = Column(UUIDType, unique=True, nullable=False, index=True)
    amount = Column(Numeric(precision=18, scale=2), nullable=False)
    kind = Column(
        Enum(KindEnum, native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    status = Column(
        Enum(StatusEnum, native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=StatusEnum.PENDING,
    )
    partner_transaction_id = Column(String(255), nullable=True)
    partner_response = Column(JSON, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<Transaction id={self.id} external_id={self.external_id} kind={self.kind} status={self.status}>"
