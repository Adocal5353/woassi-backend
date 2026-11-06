from uuid import UUID

from woassi.modules.catalog.application.dto import UploadPhoto
from woassi.modules.catalog.application.ports import (
    CatalogUnitOfWork,
    ImageProcessor,
    PhotoJobQueue,
)
from woassi.modules.catalog.domain.errors import (
    InvalidPhoto,
    PhotoAlreadyProcessed,
    PhotoNotFound,
    ProductNotFound,
    UnreadableImage,
)
from woassi.modules.catalog.domain.product import (
    DEFAULT_MAX_PHOTOS,
    PhotoStatus,
    Product,
    variant_key,
)
from woassi.shared.application.ports import StoragePort
from woassi.shared.domain.errors import ObjectNotFound

ALLOWED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_SIZE_BYTES = 8 * 1024 * 1024
VARIANT_SIZES = (400, 1024)


async def _load_product(uow: CatalogUnitOfWork, shop_id: UUID, product_id: UUID) -> Product:
    product = await uow.products.get(shop_id, product_id)
    if product is None:
        raise ProductNotFound(f"Product {product_id} not found.")
    return product


class RequestPhotoUpload:
    def __init__(
        self,
        uow: CatalogUnitOfWork,
        uploads: StoragePort,
        *,
        max_photos: int = DEFAULT_MAX_PHOTOS,
        max_size_bytes: int = MAX_SIZE_BYTES,
        expire_s: int = 600,
    ) -> None:
        self._uow = uow
        self._uploads = uploads
        self._max_photos = max_photos
        self._max_size_bytes = max_size_bytes
        self._expire_s = expire_s

    async def execute(
        self, *, shop_id: UUID, product_id: UUID, content_type: str, size: int
    ) -> UploadPhoto:
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise InvalidPhoto(f"Unsupported file type: {content_type}.")
        if size <= 0 or size > self._max_size_bytes:
            raise InvalidPhoto(f"Invalid size: maximum {self._max_size_bytes} bytes.")

        async with self._uow as uow:
            product = await _load_product(uow, shop_id, product_id)
            photo = product.add_photo(content_type=content_type, max_photos=self._max_photos)
            await uow.products.save(product)
            await uow.commit()

        upload_url = await self._uploads.presigned_put(
            photo.original_key, content_type, self._expire_s
        )
        return UploadPhoto(photo_id=photo.id, upload_url=upload_url, expire_s=self._expire_s)


class ConfirmPhoto:
    def __init__(
        self,
        uow: CatalogUnitOfWork,
        uploads: StoragePort,
        queue: PhotoJobQueue,
        *,
        max_size_bytes: int = MAX_SIZE_BYTES,
    ) -> None:
        self._uow = uow
        self._uploads = uploads
        self._queue = queue
        self._max_size_bytes = max_size_bytes

    async def execute(self, *, shop_id: UUID, product_id: UUID, photo_id: UUID) -> None:
        async with self._uow as uow:
            product = await _load_product(uow, shop_id, product_id)
            photo = product.photo(photo_id)
            if photo.status is not PhotoStatus.PENDING:
                raise PhotoAlreadyProcessed(f"Photo {photo_id} has already been processed.")

            info = await self._uploads.stat(photo.original_key)
            if info is None:
                raise InvalidPhoto("The file was not received.")

            if info.size > self._max_size_bytes:
                # The declared size proves nothing: only the size of the received object counts.
                await self._uploads.delete(photo.original_key)
                photo.reject()
                await uow.products.save(product)
                await uow.commit()
                raise InvalidPhoto(f"File too large: maximum {self._max_size_bytes} bytes.")

        await self._queue.enqueue_processing(photo_id)


class ProcessPhoto:
    """Run by the worker. No-op if the photo has already been processed."""

    def __init__(
        self,
        uow: CatalogUnitOfWork,
        uploads: StoragePort,
        images: StoragePort,
        processor: ImageProcessor,
    ) -> None:
        self._uow = uow
        self._uploads = uploads
        self._images = images
        self._processor = processor

    async def execute(self, photo_id: UUID) -> None:
        async with self._uow as uow:
            product = await uow.products.get_by_photo(photo_id)
            if product is None:
                raise PhotoNotFound(f"Photo {photo_id} not found.")
            photo = product.photo(photo_id)
            if photo.status is not PhotoStatus.PENDING:
                return

            try:
                original = await self._uploads.get(photo.original_key)
                variants = await self._processor.webp_variants(original, VARIANT_SIZES)
            except (ObjectNotFound, UnreadableImage):
                photo.reject()
            else:
                keys: dict[int, str] = {}
                for size, data in variants.items():
                    key = variant_key(product.shop_id, product.id, photo.id, size)
                    await self._images.put(key, data, "image/webp")
                    keys[size] = key
                photo.mark_ready(keys)

            await uow.products.save(product)
            await uow.commit()

        await self._uploads.delete(photo.original_key)
