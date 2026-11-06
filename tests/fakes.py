"""In-memory fake adapters for testing use cases without I/O."""

from collections.abc import Sequence
from copy import deepcopy
from types import TracebackType
from typing import Self
from uuid import UUID

from woassi.modules.catalog.domain.errors import UnreadableImage
from woassi.modules.catalog.domain.product import Product
from woassi.modules.messaging.domain.event import MetaEvent
from woassi.shared.application.ports import ObjectInfo
from woassi.shared.domain.errors import ObjectNotFound


class FakeStorage:
    def __init__(self, public_base: str | None = None) -> None:
        self.objects: dict[str, bytes] = {}
        self.public_base = public_base

    async def presigned_put(self, key: str, content_type: str, expire_s: int = 600) -> str:
        return f"http://signed/put/{key}?expire={expire_s}"

    async def presigned_get(self, key: str, expire_s: int = 3600) -> str:
        return f"http://signed/get/{key}?expire={expire_s}"

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data

    async def get(self, key: str) -> bytes:
        if key not in self.objects:
            raise ObjectNotFound(key)
        return self.objects[key]

    async def stat(self, key: str) -> ObjectInfo | None:
        if key not in self.objects:
            return None
        return ObjectInfo(key=key, size=len(self.objects[key]), content_type=None)

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def public_url(self, key: str) -> str:
        assert self.public_base is not None
        return f"{self.public_base}/{key}"


class FakeProductRepository:
    def __init__(self) -> None:
        self.products: dict[UUID, Product] = {}
        self.pending: dict[UUID, Product] = {}

    async def add(self, product: Product) -> None:
        self.pending[product.id] = deepcopy(product)

    async def get(self, shop_id: UUID, product_id: UUID) -> Product | None:
        product = self.products.get(product_id)
        return deepcopy(product) if product and product.shop_id == shop_id else None

    async def get_by_photo(self, photo_id: UUID) -> Product | None:
        for product in self.products.values():
            if any(photo.id == photo_id for photo in product.photos):
                return deepcopy(product)
        return None

    async def list(self, shop_id: UUID, offset: int, limit: int) -> Sequence[Product]:
        products = [p for p in self.products.values() if p.shop_id == shop_id]
        return deepcopy(products[offset : offset + limit])

    async def save(self, product: Product) -> None:
        self.pending[product.id] = deepcopy(product)


class FakeUoW:
    """Like a real transaction: nothing is persisted without a commit."""

    def __init__(self) -> None:
        self.repository = FakeProductRepository()

    @property
    def products(self) -> FakeProductRepository:
        return self.repository

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.rollback()

    async def commit(self) -> None:
        self.repository.products.update(self.repository.pending)
        self.repository.pending.clear()

    async def rollback(self) -> None:
        self.repository.pending.clear()


class FakeJobQueue:
    def __init__(self) -> None:
        self.photos: list[UUID] = []

    async def enqueue_processing(self, photo_id: UUID) -> None:
        self.photos.append(photo_id)


class FakeImageProcessor:
    def __init__(self, *, unreadable: bool = False) -> None:
        self.unreadable = unreadable

    async def webp_variants(self, data: bytes, sizes: Sequence[int]) -> dict[int, bytes]:
        if self.unreadable:
            raise UnreadableImage("unreadable")
        return {size: f"webp-{size}".encode() for size in sizes}


class FakeEventQueue:
    def __init__(self) -> None:
        self.events: list[MetaEvent] = []

    async def enqueue(self, event: MetaEvent) -> None:
        self.events.append(event)
