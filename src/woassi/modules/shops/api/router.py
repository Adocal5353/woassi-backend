from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from woassi.modules.shops.api.deps import ShopsDep
from woassi.modules.shops.api.schemas import (
    LogoConfirm,
    LogoUploadRequest,
    LogoUploadResponse,
    ReceivingAccountBody,
    ReceivingAccountResponse,
    SettingsBody,
    ShopCreate,
    ShopResponse,
    ShopUpdate,
    WhatsAppConnect,
    WhatsAppResponse,
)
from woassi.shared.api.deps import CurrentAccount, client_ip, get_authorized_shop
from woassi.shared.api.pagination import Limit, Offset, Page

account_router = APIRouter(prefix="/shops", tags=["shops"])
router = APIRouter(
    prefix="/shops/{shop_id}",
    tags=["shops"],
    dependencies=[Depends(get_authorized_shop)],
)


@account_router.post("", status_code=status.HTTP_201_CREATED)
async def create_shop(body: ShopCreate, account: CurrentAccount, shops: ShopsDep) -> ShopResponse:
    shop = await shops.create_shop().execute(account_id=account.id, **body.model_dump())
    return ShopResponse.from_view(shop)


@account_router.get("")
async def list_shops(
    account: CurrentAccount, shops: ShopsDep, offset: Offset = 0, limit: Limit = 50
) -> Page[ShopResponse]:
    result = await shops.list_shops().execute(account_id=account.id, offset=offset, limit=limit)
    return Page[ShopResponse].from_result(result, ShopResponse.from_view)


@router.get("")
async def get_shop(shop_id: UUID, shops: ShopsDep) -> ShopResponse:
    return ShopResponse.from_view(await shops.get_shop().execute(shop_id))


@router.patch("")
async def update_shop(shop_id: UUID, body: ShopUpdate, shops: ShopsDep) -> ShopResponse:
    shop = await shops.update_shop().execute(shop_id=shop_id, **body.model_dump(exclude_unset=True))
    return ShopResponse.from_view(shop)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def archive_shop(shop_id: UUID, shops: ShopsDep) -> None:
    await shops.archive_shop().execute(shop_id)


@router.get("/settings")
async def get_settings(shop_id: UUID, shops: ShopsDep) -> SettingsBody:
    return SettingsBody.from_view(await shops.get_settings().execute(shop_id))


@router.put("/settings")
async def replace_settings(shop_id: UUID, body: SettingsBody, shops: ShopsDep) -> SettingsBody:
    settings = await shops.replace_settings().execute(
        shop_id=shop_id,
        **body.to_arguments(),  # type: ignore[arg-type]
    )
    return SettingsBody.from_view(settings)


@router.post("/whatsapp/connect")
async def connect_whatsapp(
    shop_id: UUID, body: WhatsAppConnect, shops: ShopsDep
) -> WhatsAppResponse:
    account = await shops.connect_whatsapp().execute(shop_id=shop_id, **body.model_dump())
    return WhatsAppResponse.from_view(account)


@router.get("/whatsapp")
async def get_whatsapp(shop_id: UUID, shops: ShopsDep) -> WhatsAppResponse:
    return WhatsAppResponse.from_view(await shops.get_whatsapp().execute(shop_id))


@router.delete("/whatsapp", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_whatsapp(shop_id: UUID, shops: ShopsDep) -> None:
    await shops.disconnect_whatsapp().execute(shop_id)


@router.get("/receiving-account")
async def get_receiving_account(shop_id: UUID, shops: ShopsDep) -> ReceivingAccountResponse | None:
    account = await shops.get_receiving_account().execute(shop_id)
    return ReceivingAccountResponse.from_view(account) if account else None


@router.put("/receiving-account")
async def set_receiving_account(
    shop_id: UUID,
    body: ReceivingAccountBody,
    request: Request,
    account: CurrentAccount,
    shops: ShopsDep,
) -> ReceivingAccountResponse:
    saved = await shops.set_receiving_account().execute(
        shop_id=shop_id, account_id=account.id, ip=client_ip(request), **body.model_dump()
    )
    return ReceivingAccountResponse.from_view(saved)


@router.delete("/receiving-account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_receiving_account(
    shop_id: UUID, request: Request, account: CurrentAccount, shops: ShopsDep
) -> None:
    await shops.delete_receiving_account().execute(
        shop_id=shop_id, account_id=account.id, ip=client_ip(request)
    )


@router.post("/logo/upload-url")
async def request_logo_upload(
    shop_id: UUID, body: LogoUploadRequest, shops: ShopsDep
) -> LogoUploadResponse:
    upload = await shops.request_logo_upload().execute(
        shop_id=shop_id, content_type=body.content_type, size=body.size
    )
    return LogoUploadResponse.from_upload(upload)


@router.post("/logo/confirm")
async def confirm_logo(shop_id: UUID, body: LogoConfirm, shops: ShopsDep) -> ShopResponse:
    shop = await shops.confirm_logo().execute(shop_id=shop_id, logo_id=body.logo_id)
    return ShopResponse.from_view(shop)
