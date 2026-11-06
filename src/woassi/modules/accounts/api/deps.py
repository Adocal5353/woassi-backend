from typing import Annotated, cast

from fastapi import Depends, Request

from woassi.modules.accounts.application.facade import AccountsUseCases


def get_accounts(request: Request) -> AccountsUseCases:
    return cast(AccountsUseCases, request.app.state.container)


AccountsDep = Annotated[AccountsUseCases, Depends(get_accounts)]
