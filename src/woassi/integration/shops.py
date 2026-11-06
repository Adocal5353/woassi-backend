from uuid import UUID

from woassi.modules.messaging.application.ports import ShopConnection
from woassi.modules.shops.application.use_cases.shops import (
    CheckShopOwnership,
    ResolveShopByPhoneNumber,
)


class ShopsOwnership:
    """ShopOwnershipPort, for the shared api, backed by the shops module."""

    def __init__(self, use_case: CheckShopOwnership) -> None:
        self._use_case = use_case

    async def owns(self, account_id: UUID, shop_id: UUID) -> bool:
        return await self._use_case.execute(account_id=account_id, shop_id=shop_id)


class ShopsLookup:
    """ShopByPhoneNumberPort, for the messaging module, backed by the shops module."""

    def __init__(self, use_case: ResolveShopByPhoneNumber) -> None:
        self._use_case = use_case

    async def by_phone_number_id(self, phone_number_id: str) -> ShopConnection | None:
        routing = await self._use_case.execute(phone_number_id)
        if routing is None:
            return None
        return ShopConnection(shop_id=routing.shop_id, access_token=routing.access_token)
