from typing import Final
from uuid import UUID

from woassi.modules.accounts.application.dto import AccountView, account_view
from woassi.modules.accounts.application.ports import AccountsUnitOfWork
from woassi.shared.domain.errors import Unauthorized

# Tells "leave the email alone" apart from "remove it" (None).
UNCHANGED: Final = "__unchanged__"


class GetMyAccount:
    def __init__(self, uow: AccountsUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, account_id: UUID) -> AccountView:
        async with self._uow as uow:
            account = await uow.accounts.get(account_id)
        if account is None:
            raise Unauthorized("Authentication required.")
        return account_view(account)


class UpdateMyAccount:
    def __init__(self, uow: AccountsUnitOfWork) -> None:
        self._uow = uow

    async def execute(
        self, *, account_id: UUID, full_name: str | None = None, email: str | None = UNCHANGED
    ) -> AccountView:
        async with self._uow as uow:
            account = await uow.accounts.get(account_id)
            if account is None:
                raise Unauthorized("Authentication required.")
            if full_name is not None:
                account.rename(full_name)
            if email != UNCHANGED:
                account.change_email(email)
            await uow.accounts.save(account)
            await uow.commit()
        return account_view(account)
