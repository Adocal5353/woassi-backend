from collections.abc import Callable, Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from woassi.modules.catalog.domain.errors import ProductNotFound, RetailerIdAlreadyUsed
from woassi.modules.catalog.domain.product import PhotoStatus, Product, ProductPhoto
from woassi.modules.catalog.infrastructure.models import ProductModel, ProductPhotoModel
from woassi.shared.domain.events import Entity
from woassi.shared.domain.values import Amount


def _photo_to_domain(model: ProductPhotoModel) -> ProductPhoto:
    return ProductPhoto(
        id=model.id,
        product_id=model.product_id,
        original_key=model.original_key,
        content_type=model.content_type,
        status=PhotoStatus(model.status),
        position=model.position,
        # JSON only has string keys
        variant_keys={int(size): key for size, key in model.variants.items()},
    )


def _to_domain(model: ProductModel) -> Product:
    return Product(
        id=model.id,
        shop_id=model.shop_id,
        name=model.name,
        price=Amount(model.price),
        stock=model.stock,
        retailer_id=model.retailer_id,
        description=model.description,
        active=model.active,
        photos=[_photo_to_domain(photo) for photo in model.photos],
    )


def _copy_photo(photo: ProductPhoto, model: ProductPhotoModel) -> ProductPhotoModel:
    model.id = photo.id
    model.product_id = photo.product_id
    model.original_key = photo.original_key
    model.content_type = photo.content_type
    model.status = photo.status.value
    model.position = photo.position
    model.variants = {str(size): key for size, key in photo.variant_keys.items()}
    return model


def _copy_product(product: Product, model: ProductModel) -> ProductModel:
    existing = {photo.id: photo for photo in model.photos}
    model.id = product.id
    model.shop_id = product.shop_id
    model.name = product.name
    model.price = product.price.value
    model.stock = product.stock
    model.retailer_id = product.retailer_id
    model.description = product.description
    model.active = product.active
    model.photos = [
        _copy_photo(photo, existing.get(photo.id) or ProductPhotoModel())
        for photo in product.photos
    ]
    return model


class SqlAlchemyProductRepository:
    def __init__(self, session: AsyncSession, track: Callable[[Entity], None]) -> None:
        self._session = session
        self._track = track

    async def add(self, product: Product) -> None:
        self._session.add(_copy_product(product, ProductModel()))
        try:
            await self._session.flush()
        except IntegrityError as error:
            if "uq_products_shop_id_retailer_id" in str(error.orig):
                raise RetailerIdAlreadyUsed(
                    f"retailer_id {product.retailer_id} already exists in this shop."
                ) from error
            raise
        self._track(product)

    async def get(self, shop_id: UUID, product_id: UUID) -> Product | None:
        model = await self._session.scalar(
            select(ProductModel).where(
                ProductModel.id == product_id, ProductModel.shop_id == shop_id
            )
        )
        return _to_domain(model) if model else None

    async def get_by_photo(self, photo_id: UUID) -> Product | None:
        model = await self._session.scalar(
            select(ProductModel)
            .join(ProductPhotoModel, ProductPhotoModel.product_id == ProductModel.id)
            .where(ProductPhotoModel.id == photo_id)
        )
        return _to_domain(model) if model else None

    async def list(self, shop_id: UUID, offset: int, limit: int) -> Sequence[Product]:
        models = await self._session.scalars(
            select(ProductModel)
            .where(ProductModel.shop_id == shop_id)
            .order_by(ProductModel.created_at, ProductModel.id)
            .offset(offset)
            .limit(limit)
        )
        return [_to_domain(model) for model in models]

    async def count(self, shop_id: UUID) -> int:
        total = await self._session.scalar(
            select(func.count()).select_from(ProductModel).where(ProductModel.shop_id == shop_id)
        )
        return total or 0

    async def save(self, product: Product) -> None:
        model = await self._session.get(ProductModel, product.id)
        if model is None:
            raise ProductNotFound(f"Product {product.id} not found.")
        _copy_product(product, model)
        await self._session.flush()
        self._track(product)
