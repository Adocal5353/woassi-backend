from uuid import UUID


class DenyAllShopOwnership:
    """ShopOwnershipPort until the shops module exists: nobody owns any shop.

    TODO(shops): replace with an implementation backed by the shops module.
    """

    async def owns(self, account_id: UUID, shop_id: UUID) -> bool:
        return False
