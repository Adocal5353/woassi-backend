from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from woassi.shared.infrastructure.db.base import Base


class OutboundMessageModel(Base):
    __tablename__ = "outbound_messages"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACCEPTED', 'SENT', 'DELIVERED', 'READ', 'FAILED')", name="status_valid"
        ),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    # No FK: modules stay independent.
    shop_id: Mapped[UUID] = mapped_column(index=True)
    recipient: Mapped[str] = mapped_column(String(150))
    kind: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20))
    error_code: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
