from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from woassi.modules.catalog.api.deps import CatalogDep
from woassi.modules.catalog.api.schemas import (
    ProductCreate,
    ProductResponse,
    UploadUrlRequest,
    UploadUrlResponse,
)
from woassi.shared.api.deps import verify_shop_access

router = APIRouter(
    prefix="/shops/{shop_id}/products",
    tags=["catalog"],
    dependencies=[Depends(verify_shop_access)],
)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_product(
    shop_id: UUID, body: ProductCreate, catalog: CatalogDep
) -> ProductResponse:
    product = await catalog.create_product().execute(shop_id=shop_id, **body.model_dump())
    return ProductResponse.from_view(product)


@router.get("")
async def list_products(
    shop_id: UUID,
    catalog: CatalogDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[ProductResponse]:
    products = await catalog.list_products().execute(shop_id=shop_id, offset=offset, limit=limit)
    return [ProductResponse.from_view(product) for product in products]


@router.get("/{product_id}")
async def get_product(shop_id: UUID, product_id: UUID, catalog: CatalogDep) -> ProductResponse:
    product = await catalog.get_product().execute(shop_id=shop_id, product_id=product_id)
    return ProductResponse.from_view(product)


@router.post("/{product_id}/photos/upload-url")
async def request_photo_upload(
    shop_id: UUID, product_id: UUID, body: UploadUrlRequest, catalog: CatalogDep
) -> UploadUrlResponse:
    upload = await catalog.request_photo_upload().execute(
        shop_id=shop_id,
        product_id=product_id,
        content_type=body.content_type,
        size=body.size,
    )
    return UploadUrlResponse.from_view(upload)


@router.post("/{product_id}/photos/{photo_id}/confirm", status_code=status.HTTP_202_ACCEPTED)
async def confirm_photo(
    shop_id: UUID, product_id: UUID, photo_id: UUID, catalog: CatalogDep
) -> Response:
    await catalog.confirm_photo().execute(shop_id=shop_id, product_id=product_id, photo_id=photo_id)
    return Response(status_code=status.HTTP_202_ACCEPTED)
