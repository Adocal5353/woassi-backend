from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from woassi.modules.messaging.domain.event import MetaEvent


class EventQueue(Protocol):
    async def enqueue(self, event: MetaEvent) -> None: ...


@dataclass(frozen=True, slots=True)
class ShopConnection:
    shop_id: UUID
    access_token: str = field(repr=False)


class ShopByPhoneNumberPort(Protocol):
    async def by_phone_number_id(self, phone_number_id: str) -> ShopConnection | None:
        """None for an unknown number, or a shop that may not process messages."""
        ...
