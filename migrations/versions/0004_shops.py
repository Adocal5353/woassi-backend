"""Shops: shops, shop_settings, whatsapp_accounts and receiving_accounts

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _shop_key(table: str) -> tuple[sa.Column[object], sa.ForeignKeyConstraint]:
    return (
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["shop_id"], ["shops.id"], name=op.f(f"fk_{table}_shop_id_shops"), ondelete="CASCADE"
        ),
    )


def upgrade() -> None:
    op.create_table(
        "shops",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("address", sa.String(length=300), nullable=False),
        sa.Column("logo_key", sa.String(length=300), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'SUSPENDED')", name=op.f("ck_shops_status_valid")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shops")),
        sa.UniqueConstraint("slug", name=op.f("uq_shops_slug")),
    )
    op.create_index(op.f("ix_shops_account_id"), "shops", ["account_id"], unique=False)

    column, foreign_key = _shop_key("shop_settings")
    op.create_table(
        "shop_settings",
        column,
        sa.Column("notification_number", sa.String(length=16), nullable=True),
        sa.Column("payment_modes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reminder_1_minutes", sa.Integer(), nullable=False),
        sa.Column("reminder_2_minutes", sa.Integer(), nullable=False),
        sa.Column("expiration_hours", sa.Integer(), nullable=False),
        sa.Column("welcome_message", sa.Text(), nullable=False),
        sa.Column("invoice_details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("invoice_prefix", sa.String(length=10), nullable=False),
        foreign_key,
        sa.PrimaryKeyConstraint("shop_id", name=op.f("pk_shop_settings")),
    )

    column, foreign_key = _shop_key("whatsapp_accounts")
    op.create_table(
        "whatsapp_accounts",
        column,
        sa.Column("waba_id", sa.String(length=64), nullable=False),
        sa.Column("phone_number_id", sa.String(length=64), nullable=True),
        sa.Column("display_phone_number", sa.String(length=32), nullable=True),
        sa.Column("verified_name", sa.String(length=255), nullable=True),
        sa.Column("catalog_id", sa.String(length=64), nullable=True),
        sa.Column("encrypted_token", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "status IN ('IN_PROGRESS', 'CONNECTED', 'ERROR', 'DISCONNECTED')",
            name=op.f("ck_whatsapp_accounts_status_valid"),
        ),
        foreign_key,
        sa.PrimaryKeyConstraint("shop_id", name=op.f("pk_whatsapp_accounts")),
        sa.UniqueConstraint("phone_number_id", name=op.f("uq_whatsapp_accounts_phone_number_id")),
    )

    column, foreign_key = _shop_key("receiving_accounts")
    op.create_table(
        "receiving_accounts",
        column,
        sa.Column("operator", sa.String(length=10), nullable=False),
        sa.Column("number", sa.String(length=16), nullable=False),
        sa.Column("holder_name", sa.String(length=200), nullable=False),
        sa.Column("encrypted_merchant_id", sa.Text(), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "operator IN ('MIXX', 'MOOV')", name=op.f("ck_receiving_accounts_operator_valid")
        ),
        foreign_key,
        sa.PrimaryKeyConstraint("shop_id", name=op.f("pk_receiving_accounts")),
    )


def downgrade() -> None:
    op.drop_table("receiving_accounts")
    op.drop_table("whatsapp_accounts")
    op.drop_table("shop_settings")
    op.drop_index(op.f("ix_shops_account_id"), table_name="shops")
    op.drop_table("shops")
