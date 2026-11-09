from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from woassi.modules.customers.domain.customer import Customer
from woassi.shared.application.ports import UnitOfWork
from woassi.shared.domain.values import PhoneNumber


class CustomerRepository(Protocol):
    async def add(self, customer: Customer) -> None: ...

    async def get(self, shop_id: UUID, customer_id: UUID) -> Customer | None: ...

    async def find(
        self, shop_id: UUID, *, user_id: str | None, phone: PhoneNumber | None
    ) -> Customer | None:
        """By user id first, then by phone number. Locks the row it returns."""
        ...

    async def list(self, shop_id: UUID, offset: int, limit: int) -> Sequence[Customer]: ...

    async def count(self, shop_id: UUID) -> int: ...

    async def save(self, customer: Customer) -> None: ...


class CustomersUnitOfWork(UnitOfWork, Protocol):
    @property
    def customers(self) -> CustomerRepository: ...
