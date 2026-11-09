from uuid import UUID

from woassi.modules.messaging.application.ports import ShopConnection
from woassi.modules.shops.application.dto import ShopRouting
from woassi.modules.shops.application.use_cases.shops import (
    CheckShopOwnership,
    ResolveShopByPhoneNumber,
    ResolveShopConnection,
)
from woassi.modules.shops.application.use_cases.whatsapp import HandleWhatsAppAccountRemoved


class ShopsOwnership:
    """ShopOwnershipPort, for the shared api, backed by the shops module."""

    def __init__(self, use_case: CheckShopOwnership) -> None:
        self._use_case = use_case

    async def owns(self, account_id: UUID, shop_id: UUID) -> bool:
        return await self._use_case.execute(account_id=account_id, shop_id=shop_id)


def _connection(routing: ShopRouting | None) -> ShopConnection | None:
    if routing is None:
        return None
    return ShopConnection(
        shop_id=routing.shop_id,
        phone_number_id=routing.phone_number_id,
        access_token=routing.access_token,
    )


class ShopsConnections:
    """ShopConnectionsPort, for the messaging module, backed by the shops module."""

    def __init__(
        self, by_phone_number: ResolveShopByPhoneNumber, by_shop: ResolveShopConnection
    ) -> None:
        self._by_phone_number = by_phone_number
        self._by_shop = by_shop

    async def by_phone_number_id(self, phone_number_id: str) -> ShopConnection | None:
        return _connection(await self._by_phone_number.execute(phone_number_id))

    async def by_shop_id(self, shop_id: UUID) -> ShopConnection | None:
        return _connection(await self._by_shop.execute(shop_id))


class ShopsWhatsAppAccounts:
    """WhatsAppAccountsPort, for the messaging module, backed by the shops module."""

    def __init__(self, use_case: HandleWhatsAppAccountRemoved) -> None:
        self._use_case = use_case

    async def account_removed(self, waba_id: str) -> int:
        return await self._use_case.execute(waba_id)
