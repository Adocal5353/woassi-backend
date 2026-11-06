from typing import Annotated
from uuid import UUID

from fastapi import Depends


async def get_current_account() -> None:
    """TODO(auth): read the JWT and return the current Account; 401 if missing or invalid."""
    return None


async def verify_shop_access(
    shop_id: UUID,
    account: Annotated[None, Depends(get_current_account)],
) -> UUID:
    """TODO(auth): check that the shop belongs to the current account; 403 otherwise.

    Until this check exists, anyone can access any shop.
    """
    return shop_id
