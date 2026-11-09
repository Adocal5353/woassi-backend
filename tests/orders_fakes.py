"""In-memory adapters for the orders module, and a stack wiring them to the real use cases."""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from types import TracebackType
from typing import Self
from uuid import UUID, uuid4

from tests.fakes import FakeAuditLog
from woassi.modules.orders.application.ports import (
    Contact,
    DuplicateOrder,
    Notification,
    NotificationNotSent,
    ShopProfile,
    StockItem,
    Template,
)
from woassi.modules.orders.application.use_cases.orders import (
    Cart,
    DecideOrder,
    OrderFlow,
    ProcessDueOrders,
    ReceiveCart,
    ReplyToOrder,
)
from woassi.modules.orders.domain.order import Order, OrderStatus, ValidationMode
from woassi.shared.domain.events import DomainEvent
from woassi.shared.infrastructure.clock import FrozenClock

CUSTOMER = Contact(user_id="TG.123", phone="22891234567", name="Ama")
MERCHANT_PHONE = "+22890000001"


class FakeOrders:
    def __init__(self, uow: "FakeOrdersUoW") -> None:
        self._uow = uow

    def _store(self, order: Order) -> None:
        stored = deepcopy(order)
        stored.pull_events()
        self._uow.state[order.id] = stored
        self._uow.tracked.append(order)

    async def add(self, order: Order) -> None:
        for other in self._uow.state.values():
            if (
                other.shop_id == order.shop_id
                and other.source_message_id == order.source_message_id
            ):
                raise DuplicateOrder(order.source_message_id)
        self._store(order)

    async def get(self, shop_id: UUID, order_id: UUID, *, lock: bool = False) -> Order | None:
        order = self._uow.state.get(order_id)
        return deepcopy(order) if order and order.shop_id == shop_id else None

    async def get_by_source_message(self, shop_id: UUID, message_id: str) -> Order | None:
        for order in self._uow.state.values():
            if order.shop_id == shop_id and order.source_message_id == message_id:
                return deepcopy(order)
        return None

    async def list(
        self, shop_id: UUID, status: OrderStatus | None, offset: int, limit: int
    ) -> Sequence[Order]:
        orders = [
            o
            for o in self._uow.state.values()
            if o.shop_id == shop_id and (status is None or o.status is status)
        ]
        return deepcopy(sorted(orders, key=lambda o: o.created_at, reverse=True))[
            offset : offset + limit
        ]

    async def count(self, shop_id: UUID, status: OrderStatus | None) -> int:
        return len(await self.list(shop_id, status, 0, 10_000))

    async def list_due(self, now: datetime, limit: int) -> Sequence[tuple[UUID, UUID]]:
        due = [
            o
            for o in self._uow.state.values()
            if o.next_deadline is not None and o.next_deadline <= now
        ]
        due.sort(key=lambda o: o.next_deadline)  # type: ignore[arg-type, return-value]
        return [(o.shop_id, o.id) for o in due[:limit]]

    async def next_number(self, shop_id: UUID) -> int:
        self._uow.counters[shop_id] = self._uow.counters.get(shop_id, 0) + 1
        return self._uow.counters[shop_id]

    async def save(self, order: Order) -> None:
        self._store(order)


class FakeOrdersUoW:
    def __init__(self, stack: "OrdersStack") -> None:
        self.stack = stack
        self.state: dict[UUID, Order] = {}
        self.counters: dict[UUID, int] = {}
        self.tracked: list[Order] = []

    @property
    def orders(self) -> FakeOrders:
        return FakeOrders(self)

    @property
    def audit(self) -> FakeAuditLog:
        return self.stack.audit_log

    async def __aenter__(self) -> Self:
        self.state = deepcopy(self.stack.orders)
        self.counters = dict(self.stack.counters)
        self.tracked = []
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.tracked = []

    async def commit(self) -> None:
        self.stack.orders = deepcopy(self.state)
        self.stack.counters = dict(self.counters)
        for order in self.tracked:
            self.stack.events.extend(order.pull_events())
        self.tracked = []

    async def rollback(self) -> None:
        self.tracked = []


class FakeShops:
    def __init__(self, profile: ShopProfile | None) -> None:
        self.current = profile

    async def profile(self, shop_id: UUID) -> ShopProfile | None:
        return self.current if self.current and self.current.shop_id == shop_id else None


class FakeCatalog:
    """retailer_id -> (product id, name, price, stock)."""

    def __init__(self) -> None:
        self.products: dict[str, list[object]] = {}

    def add(self, retailer_id: str, name: str, price: int, stock: int) -> UUID:
        product_id = uuid4()
        self.products[retailer_id] = [product_id, name, price, stock]
        return product_id

    def stock(self, retailer_id: str) -> int:
        return self.products[retailer_id][3]  # type: ignore[return-value]

    async def reserve(self, shop_id: UUID, requested: Mapping[str, int]) -> list[StockItem]:
        items = []
        for retailer_id, quantity in requested.items():
            product = self.products.get(retailer_id)
            if product is None:
                items.append(StockItem(retailer_id, None, retailer_id, 0, quantity, 0))
                continue
            product_id, name, price, stock = product
            reserved = min(quantity, stock)  # type: ignore[type-var]
            product[3] = stock - reserved  # type: ignore[operator]
            items.append(StockItem(retailer_id, product_id, name, price, quantity, reserved))  # type: ignore[arg-type]
        return items

    async def release(self, shop_id: UUID, quantities: Mapping[UUID, int]) -> None:
        for product in self.products.values():
            if product[0] in quantities:
                product[3] = product[3] + quantities[product[0]]  # type: ignore[assignment, operator]


class FakeCustomers:
    def __init__(self) -> None:
        self.contacts: dict[UUID, Contact] = {}

    async def contact(self, shop_id: UUID, customer_id: UUID) -> Contact:
        return self.contacts.get(customer_id, Contact())


class RecordingMessaging:
    def __init__(self) -> None:
        self.sent: list[tuple[Contact, Notification, str, str]] = []
        self.failing = False

    async def send(
        self, shop_id: UUID, to: Contact, notification: Notification, *, kind: str
    ) -> str:
        if self.failing:
            raise NotificationNotSent("messaging.message_not_sent")
        message_id = f"wamid.{len(self.sent) + 1}"
        self.sent.append((to, notification, kind, message_id))
        return message_id

    def to_merchant(self) -> list[tuple[Template, str]]:
        return [
            (n, mid)
            for to, n, _, mid in self.sent
            if to.phone == MERCHANT_PHONE and isinstance(n, Template)
        ]

    def to_customer(self) -> list[tuple[Notification, str]]:
        return [(n, mid) for to, n, _, mid in self.sent if to.phone != MERCHANT_PHONE]


def profile(
    shop_id: UUID,
    *,
    mode: ValidationMode = ValidationMode.MANUAL,
    max_amount: int | None = None,
    language: str = "fr",
    notification_number: str | None = MERCHANT_PHONE,
) -> ShopProfile:
    return ShopProfile(
        shop_id=shop_id,
        account_id=uuid4(),
        name="Chez Ama",
        language=language,
        validation_mode=mode,
        auto_validation_max_amount=max_amount,
        notification_number=notification_number,
        reminder_1_minutes=15,
        reminder_2_minutes=60,
        expiration_hours=24,
    )


class OrdersStack:
    def __init__(self, **profile_options: object) -> None:
        self.shop_id = uuid4()
        self.customer_id = uuid4()
        self.orders: dict[UUID, Order] = {}
        self.counters: dict[UUID, int] = {}
        self.events: list[DomainEvent] = []
        self.audit_log = FakeAuditLog()
        self.shops = FakeShops(profile(self.shop_id, **profile_options))  # type: ignore[arg-type]
        self.catalog = FakeCatalog()
        self.customers = FakeCustomers()
        self.customers.contacts[self.customer_id] = CUSTOMER
        self.messaging = RecordingMessaging()
        self.clock = FrozenClock(datetime(2026, 1, 1, 9, tzinfo=UTC))

    def _flow[F: OrderFlow](self, use_case: type[F]) -> F:
        return use_case(
            FakeOrdersUoW(self),
            self.shops,
            self.catalog,
            self.customers,
            self.messaging,
            self.clock,
        )

    async def receive(self, *items: tuple[str, int], message_id: str = "wamid.CART") -> Order:
        order_id = await self._flow(ReceiveCart).execute(
            shop_id=self.shop_id,
            cart=Cart(message_id=message_id, customer_id=self.customer_id, items=items),
        )
        assert order_id is not None
        return self.orders[order_id]

    async def reply(self, payload: str, context: str | None) -> bool:
        return await self._flow(ReplyToOrder).execute(
            shop_id=self.shop_id, payload=payload, context_message_id=context
        )

    async def decide(self, order: Order, accept: bool) -> Order:
        return await self._flow(DecideOrder).execute(
            shop_id=self.shop_id, order_id=order.id, accept=accept, account_id=uuid4()
        )

    async def tick(self) -> int:
        return await self._flow(ProcessDueOrders).execute()

    def order(self, order: Order) -> Order:
        return self.orders[order.id]
