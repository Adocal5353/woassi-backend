from dataclasses import dataclass
from uuid import UUID

from woassi.shared.domain.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class ShopCreated(DomainEvent):
    shop_id: UUID
    account_id: UUID


@dataclass(frozen=True, kw_only=True)
class WhatsAppConnected(DomainEvent):
    shop_id: UUID
    phone_number_id: str


@dataclass(frozen=True, kw_only=True)
class ReceivingAccountChanged(DomainEvent):
    shop_id: UUID
