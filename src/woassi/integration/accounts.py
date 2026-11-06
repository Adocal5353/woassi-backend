from woassi.modules.accounts.application.use_cases.session import AuthenticateAccount
from woassi.shared.application.ports import AuthenticatedAccount


class AccountsAuthenticator:
    """AccountAuthenticator, for the shared api, backed by the accounts module."""

    def __init__(self, use_case: AuthenticateAccount) -> None:
        self._use_case = use_case

    async def authenticate(self, access_token: str) -> AuthenticatedAccount:
        return AuthenticatedAccount(id=await self._use_case.execute(access_token))
