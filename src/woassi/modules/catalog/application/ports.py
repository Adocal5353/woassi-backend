from collections.abc import Sequence
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from woassi.modules.catalog.domain.product import Product


class ProductRepository(Protocol):
    async def add(self, product: Product) -> None: ...

    async def get(self, shop_id: UUID, product_id: UUID) -> Product | None: ...

    async def get_by_photo(self, photo_id: UUID) -> Product | None: ...

    async def list(self, shop_id: UUID, offset: int, limit: int) -> Sequence[Product]: ...

    async def save(self, product: Product) -> None: ...


class CatalogUnitOfWork(Protocol):
    @property
    def products(self) -> ProductRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class PhotoJobQueue(Protocol):
    async def enqueue_processing(self, photo_id: UUID) -> None: ...


class ImageProcessor(Protocol):
    async def webp_variants(self, data: bytes, sizes: Sequence[int]) -> dict[int, bytes]:
        """Return one WebP image per size. Raise UnreadableImage if `data` is unusable."""
        ...
