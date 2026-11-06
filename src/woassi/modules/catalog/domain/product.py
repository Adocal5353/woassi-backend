from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID, uuid4

from woassi.modules.catalog.domain.errors import (
    InsufficientStock,
    InvalidProduct,
    PhotoNotFound,
    TooManyPhotos,
)
from woassi.shared.domain.values import Amount

DEFAULT_MAX_PHOTOS = 5


def original_key(shop_id: UUID, product_id: UUID, photo_id: UUID) -> str:
    return f"shops/{shop_id}/products/{product_id}/originals/{photo_id}"


def variant_key(shop_id: UUID, product_id: UUID, photo_id: UUID, size: int) -> str:
    return f"shops/{shop_id}/products/{product_id}/{photo_id}_{size}.webp"


class PhotoStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    REJECTED = "REJECTED"


@dataclass(slots=True)
class ProductPhoto:
    id: UUID
    product_id: UUID
    original_key: str
    content_type: str
    status: PhotoStatus
    position: int
    variant_keys: dict[int, str] = field(default_factory=dict)

    def mark_ready(self, variant_keys: dict[int, str]) -> None:
        self.status = PhotoStatus.READY
        self.variant_keys = dict(variant_keys)

    def reject(self) -> None:
        self.status = PhotoStatus.REJECTED


@dataclass(slots=True)
class Product:
    id: UUID
    shop_id: UUID
    name: str
    price: Amount
    stock: int
    retailer_id: str
    description: str = ""
    active: bool = True
    photos: list[ProductPhoto] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        shop_id: UUID,
        name: str,
        price: Amount,
        stock: int,
        retailer_id: str,
        description: str = "",
    ) -> "Product":
        name = name.strip()
        retailer_id = retailer_id.strip()
        if not name:
            raise InvalidProduct("Product name is required.")
        if not retailer_id:
            raise InvalidProduct("Product retailer_id is required.")
        if stock < 0:
            raise InvalidProduct("Stock cannot be negative.")
        return cls(
            id=uuid4(),
            shop_id=shop_id,
            name=name,
            price=price,
            stock=stock,
            retailer_id=retailer_id,
            description=description,
        )

    def adjust_stock(self, delta: int) -> None:
        if self.stock + delta < 0:
            raise InsufficientStock(f"Insufficient stock for {self.name}: {self.stock} available.")
        self.stock += delta

    def add_photo(self, *, content_type: str, max_photos: int = DEFAULT_MAX_PHOTOS) -> ProductPhoto:
        # A rejected photo must not use up a slot for good.
        active_photos = [p for p in self.photos if p.status is not PhotoStatus.REJECTED]
        if len(active_photos) >= max_photos:
            raise TooManyPhotos(f"A product cannot have more than {max_photos} photos.")
        photo_id = uuid4()
        photo = ProductPhoto(
            id=photo_id,
            product_id=self.id,
            original_key=original_key(self.shop_id, self.id, photo_id),
            content_type=content_type,
            status=PhotoStatus.PENDING,
            position=max((p.position for p in self.photos), default=-1) + 1,
        )
        self.photos.append(photo)
        return photo

    def photo(self, photo_id: UUID) -> ProductPhoto:
        for photo in self.photos:
            if photo.id == photo_id:
                return photo
        raise PhotoNotFound(f"Photo {photo_id} not found.")
