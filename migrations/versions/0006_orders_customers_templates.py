"""Orders, customers, message templates, and the order settings of shops

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORDER_STATUSES = (
    "'AWAITING_CUSTOMER', 'AWAITING_MERCHANT', 'CONFIRMED', 'REJECTED', 'CANCELLED', 'EXPIRED'"
)


def upgrade() -> None:
    # Existing shops keep today's behaviour: French, every order validated by hand.
    op.add_column(
        "shop_settings",
        sa.Column("language", sa.String(length=5), server_default="fr", nullable=False),
    )
    op.add_column(
        "shop_settings",
        sa.Column("validation_mode", sa.String(length=20), server_default="MANUAL", nullable=False),
    )
    op.add_column(
        "shop_settings", sa.Column("auto_validation_max_amount", sa.BigInteger(), nullable=True)
    )
    op.alter_column("shop_settings", "language", server_default=None)
    op.alter_column("shop_settings", "validation_mode", server_default=None)

    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(length=150), nullable=True),
        sa.Column("phone", sa.String(length=16), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
        sa.UniqueConstraint("shop_id", "user_id", name=op.f("uq_customers_shop_id_user_id")),
    )
    op.create_index("ix_customers_shop_id_phone", "customers", ["shop_id", "phone"], unique=False)

    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("source_message_id", sa.String(length=128), nullable=False),
        sa.Column("lines", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("total", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("deadlines", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("awaiting_merchant_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_reminder_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminders_sent", sa.Integer(), nullable=False),
        sa.Column("merchant_message_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("offer_message_id", sa.String(length=128), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closing_reason", sa.String(length=30), nullable=True),
        sa.Column("decided_by", sa.String(length=20), nullable=True),
        sa.CheckConstraint(f"status IN ({ORDER_STATUSES})", name=op.f("ck_orders_status_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
        sa.UniqueConstraint("shop_id", "number", name=op.f("uq_orders_shop_id_number")),
        sa.UniqueConstraint(
            "shop_id", "source_message_id", name=op.f("uq_orders_shop_id_source_message_id")
        ),
    )
    op.create_index(op.f("ix_orders_customer_id"), "orders", ["customer_id"], unique=False)
    op.create_index(
        "ix_orders_shop_id_created_at", "orders", ["shop_id", "created_at"], unique=False
    )
    op.create_index(
        "ix_orders_next_deadline",
        "orders",
        ["next_deadline"],
        unique=False,
        postgresql_where=sa.text("next_deadline IS NOT NULL"),
    )
    op.create_table(
        "order_counters",
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("shop_id", name=op.f("pk_order_counters")),
    )

    op.create_table(
        "message_templates",
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("waba_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("meta_template_id", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("shop_id", "name", "language", name=op.f("pk_message_templates")),
    )
    op.create_index(
        op.f("ix_message_templates_waba_id"), "message_templates", ["waba_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_message_templates_waba_id"), table_name="message_templates")
    op.drop_table("message_templates")
    op.drop_table("order_counters")
    op.drop_index("ix_orders_next_deadline", table_name="orders")
    op.drop_index("ix_orders_shop_id_created_at", table_name="orders")
    op.drop_index(op.f("ix_orders_customer_id"), table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_customers_shop_id_phone", table_name="customers")
    op.drop_table("customers")
    op.drop_column("shop_settings", "auto_validation_max_amount")
    op.drop_column("shop_settings", "validation_mode")
    op.drop_column("shop_settings", "language")
