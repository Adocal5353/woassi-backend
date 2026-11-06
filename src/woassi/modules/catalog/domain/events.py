from dataclasses import dataclass
from uuid import UUID

from woassi.shared.domain.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class ProductCreated(DomainEvent):
    product_id: UUID
    shop_id: UUID
    retailer_id: str
