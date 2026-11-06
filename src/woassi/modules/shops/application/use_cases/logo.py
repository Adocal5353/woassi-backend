from uuid import UUID, uuid4

from woassi.modules.shops.application.dto import LogoUpload, ShopView, shop_view
from woassi.modules.shops.application.ports import LogoProcessor, ShopsUnitOfWork
from woassi.modules.shops.application.use_cases.support import load_shop
from woassi.modules.shops.domain.errors import InvalidLogo
from woassi.modules.shops.domain.shop import logo_key, original_logo_key
from woassi.shared.application.ports import StoragePort

ALLOWED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_SIZE_BYTES = 8 * 1024 * 1024


class RequestLogoUpload:
    def __init__(self, uow: ShopsUnitOfWork, uploads: StoragePort, *, expire_s: int = 600) -> None:
        self._uow = uow
        self._uploads = uploads
        self._expire_s = expire_s

    async def execute(self, *, shop_id: UUID, content_type: str, size: int) -> LogoUpload:
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise InvalidLogo(f"Unsupported file type: {content_type}.")
        if not 0 < size <= MAX_SIZE_BYTES:
            raise InvalidLogo(f"Invalid size: maximum {MAX_SIZE_BYTES} bytes.")
        async with self._uow as uow:
            await load_shop(uow, shop_id)
        logo_id = uuid4()
        url = await self._uploads.presigned_put(
            original_logo_key(shop_id, logo_id), content_type, self._expire_s
        )
        return LogoUpload(logo_id=logo_id, upload_url=url, expire_s=self._expire_s)


class ConfirmLogo:
    def __init__(
        self,
        uow: ShopsUnitOfWork,
        uploads: StoragePort,
        images: StoragePort,
        processor: LogoProcessor,
    ) -> None:
        self._uow = uow
        self._uploads = uploads
        self._images = images
        self._processor = processor

    async def execute(self, *, shop_id: UUID, logo_id: UUID) -> ShopView:
        original = original_logo_key(shop_id, logo_id)
        info = await self._uploads.stat(original)
        if info is None:
            raise InvalidLogo("The file was not received.")
        try:
            if info.size > MAX_SIZE_BYTES:
                raise InvalidLogo(f"File too large: maximum {MAX_SIZE_BYTES} bytes.")
            webp = await self._processor.to_webp(await self._uploads.get(original))
        except InvalidLogo:
            await self._uploads.delete(original)
            raise

        key = logo_key(shop_id, logo_id)
        await self._images.put(key, webp, "image/webp")
        async with self._uow as uow:
            shop = await load_shop(uow, shop_id)
            previous = shop.logo_key
            shop.logo_key = key
            await uow.shops.save(shop)
            await uow.commit()

        await self._uploads.delete(original)
        if previous is not None and previous != key:
            await self._images.delete(previous)
        return shop_view(shop, self._images)
