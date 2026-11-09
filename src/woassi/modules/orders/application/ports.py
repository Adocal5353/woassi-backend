from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from woassi.modules.orders.domain.order import Order, OrderStatus, ValidationMode
from woassi.shared.application.ports import UnitOfWork


class OrderRepository(Protocol):
    async def add(self, order: Order) -> None:
        """Raise DuplicateOrder if this cart message already gave an order."""
        ...

    async def get(self, shop_id: UUID, order_id: UUID, *, lock: bool = False) -> Order | None: ...

    async def get_by_source_message(self, shop_id: UUID, message_id: str) -> Order | None: ...

    async def list(
        self, shop_id: UUID, status: OrderStatus | None, offset: int, limit: int
    ) -> Sequence[Order]: ...

    async def count(self, shop_id: UUID, status: OrderStatus | None) -> int: ...

    async def list_due(self, now: datetime, limit: int) -> Sequence[tuple[UUID, UUID]]:
        """(shop_id, order_id) of the open orders that need attention, oldest first."""
        ...

    async def next_number(self, shop_id: UUID) -> int: ...

    async def save(self, order: Order) -> None: ...


class OrdersUnitOfWork(UnitOfWork, Protocol):
    @property
    def orders(self) -> OrderRepository: ...


class DuplicateOrder(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ShopProfile:
    shop_id: UUID
    account_id: UUID
    name: str
    language: str
    validation_mode: ValidationMode
    auto_validation_max_amount: int | None
    notification_number: str | None = field(repr=False)
    reminder_1_minutes: int
    reminder_2_minutes: int
    expiration_hours: int


class ShopsPort(Protocol):
    async def profile(self, shop_id: UUID) -> ShopProfile | None: ...


@dataclass(frozen=True, slots=True)
class StockItem:
    retailer_id: str
    product_id: UUID | None
    name: str
    unit_price: int
    requested: int
    reserved: int


class CatalogPort(Protocol):
    async def reserve(self, shop_id: UUID, requested: Mapping[str, int]) -> list[StockItem]: ...

    async def release(self, shop_id: UUID, quantities: Mapping[UUID, int]) -> None: ...


@dataclass(frozen=True, slots=True)
class Contact:
    """Where to reach a customer: by WhatsApp user id, or by phone number."""

    user_id: str | None = field(default=None, repr=False)
    phone: str | None = field(default=None, repr=False)
    name: str | None = field(default=None, repr=False)


class CustomersPort(Protocol):
    async def contact(self, shop_id: UUID, customer_id: UUID) -> Contact:
        """An empty Contact if the customer is gone: messages to them are then skipped."""
        ...


@dataclass(frozen=True, slots=True)
class Text:
    body: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class Buttons:
    body: str = field(repr=False)
    buttons: tuple[tuple[str, str], ...]  # (id, title)


@dataclass(frozen=True, slots=True)
class Template:
    name: str
    language: str
    parameters: Mapping[str, str] = field(repr=False)
    button_payloads: tuple[str, ...] = ()


type Notification = Text | Buttons | Template


class NotificationNotSent(Exception):
    """Carries no customer data. The order goes on: the dashboard shows it anyway."""


class MessagingPort(Protocol):
    async def send(
        self, shop_id: UUID, to: Contact, notification: Notification, *, kind: str
    ) -> str:
        """Return the message id. Raise NotificationNotSent otherwise."""
        ...
