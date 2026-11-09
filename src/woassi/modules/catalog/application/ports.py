from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from woassi.modules.catalog.domain.product import Product
from woassi.shared.application.ports import UnitOfWork


class ProductRepository(Protocol):
    async def add(self, product: Product) -> None: ...

    async def get(self, shop_id: UUID, product_id: UUID) -> Product | None: ...

    async def get_by_photo(self, photo_id: UUID) -> Product | None: ...

    async def list(self, shop_id: UUID, offset: int, limit: int) -> Sequence[Product]: ...

    async def count(self, shop_id: UUID) -> int: ...

    async def list_for_update(
        self, shop_id: UUID, *, retailer_ids: Sequence[str] = (), ids: Sequence[UUID] = ()
    ) -> Sequence[Product]:
        """Lock the matching products until the end of the transaction."""
        ...

    async def save(self, product: Product) -> None: ...


class CatalogUnitOfWork(UnitOfWork, Protocol):
    @property
    def products(self) -> ProductRepository: ...


class PhotoJobQueue(Protocol):
    async def enqueue_processing(self, photo_id: UUID) -> None: ...


class ImageProcessor(Protocol):
    async def webp_variants(self, data: bytes, sizes: Sequence[int]) -> dict[int, bytes]:
        """Return one WebP image per size. Raise UnreadableImage if `data` is unusable."""
        ...
