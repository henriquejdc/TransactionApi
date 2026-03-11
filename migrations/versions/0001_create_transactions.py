"""create transactions table

Revision ID: 0001
Revises:
Create Date: 2026-03-10 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models import KindEnum

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("external_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(KindEnum.CREDIT, KindEnum.DEBIT, name="kindenum"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("pending", "processed", "failed", name="statusenum"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("partner_transaction_id", sa.String(255), nullable=True),
        sa.Column("partner_response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_transactions_id", "transactions", ["id"])
    op.create_index("ix_transactions_external_id", "transactions", ["external_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_transactions_external_id", table_name="transactions")
    op.drop_index("ix_transactions_id", table_name="transactions")
    op.drop_table("transactions")
    op.execute("DROP TYPE IF EXISTS kindenum")
    op.execute("DROP TYPE IF EXISTS statusenum")
