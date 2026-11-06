"""Catalog: products and product_photos

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        # No FK to shops yet: the shops module does not exist.
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("price", sa.BigInteger(), nullable=False),
        sa.Column("stock", sa.Integer(), nullable=False),
        sa.Column("retailer_id", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("price >= 0", name=op.f("ck_products_price_positive")),
        sa.CheckConstraint("stock >= 0", name=op.f("ck_products_stock_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint("shop_id", "retailer_id", name=op.f("uq_products_shop_id_retailer_id")),
    )
    op.create_table(
        "product_photos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("original_key", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "variants",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'READY', 'REJECTED')",
            name=op.f("ck_product_photos_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_photos_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_photos")),
    )
    op.create_index(
        op.f("ix_product_photos_product_id"), "product_photos", ["product_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_product_photos_product_id"), table_name="product_photos")
    op.drop_table("product_photos")
    op.drop_table("products")
