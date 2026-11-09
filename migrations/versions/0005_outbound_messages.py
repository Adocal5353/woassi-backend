"""Messaging: outbound_messages

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbound_messages",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("recipient", sa.String(length=150), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_code", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('ACCEPTED', 'SENT', 'DELIVERED', 'READ', 'FAILED')",
            name=op.f("ck_outbound_messages_status_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbound_messages")),
    )
    op.create_index(
        op.f("ix_outbound_messages_shop_id"), "outbound_messages", ["shop_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_outbound_messages_shop_id"), table_name="outbound_messages")
    op.drop_table("outbound_messages")
