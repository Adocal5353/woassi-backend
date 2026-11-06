from uuid import UUID, uuid4

from woassi.modules.accounts.application.dto import TokenPair
from woassi.modules.accounts.application.limits import (
    LOGIN_LIMIT,
    LOGIN_WINDOW_S,
    enforce,
    login_ip_key,
    login_phone_key,
)
from woassi.modules.accounts.application.ports import (
    AccountsUnitOfWork,
    InvalidAccessToken,
    PasswordHasher,
    TokenService,
)
from woassi.modules.accounts.application.use_cases.support import issue_tokens, parse_phone
from woassi.modules.accounts.domain.errors import InvalidCredentials, InvalidRefreshToken
from woassi.shared.application.ports import Clock, PhoneNormalizer, RateLimiter
from woassi.shared.domain.errors import Unauthorized


class Login:
    def __init__(
        self,
        uow: AccountsUnitOfWork,
        hasher: PasswordHasher,
        tokens: TokenService,
        limiter: RateLimiter,
        phones: PhoneNormalizer,
        clock: Clock,
        *,
        refresh_ttl_s: int,
    ) -> None:
        self._uow = uow
        self._hasher = hasher
        self._tokens = tokens
        self._limiter = limiter
        self._phones = phones
        self._clock = clock
        self._refresh_ttl_s = refresh_ttl_s

    async def execute(self, *, phone: str, password: str, ip: str) -> TokenPair:
        normalized = parse_phone(self._phones, phone)
        phone_key = login_phone_key(normalized.value if normalized else phone)
        ip_key = login_ip_key(ip)
        await enforce(self._limiter, ip_key, LOGIN_LIMIT, LOGIN_WINDOW_S)
        await enforce(self._limiter, phone_key, LOGIN_LIMIT, LOGIN_WINDOW_S)

        async with self._uow as uow:
            account = await uow.accounts.get_by_phone(normalized) if normalized else None
            if account is None:
                await self._hasher.dummy_verify(password)
                raise InvalidCredentials("Invalid credentials.")
            if not await self._hasher.verify(password, account.password_hash):
                raise InvalidCredentials("Invalid credentials.")

            account.record_login(self._clock.now())
            await uow.accounts.save(account)
            pair = await issue_tokens(
                uow,
                self._tokens,
                self._clock,
                account_id=account.id,
                family_id=uuid4(),
                refresh_ttl_s=self._refresh_ttl_s,
            )
            await uow.commit()

        # Only failures count: many users can share one IP behind a mobile carrier's NAT.
        await self._limiter.forgive(ip_key)
        await self._limiter.forgive(phone_key)
        return pair


class RefreshTokens:
    def __init__(
        self,
        uow: AccountsUnitOfWork,
        tokens: TokenService,
        clock: Clock,
        *,
        refresh_ttl_s: int,
    ) -> None:
        self._uow = uow
        self._tokens = tokens
        self._clock = clock
        self._refresh_ttl_s = refresh_ttl_s

    async def execute(self, refresh_token: str) -> TokenPair:
        now = self._clock.now()
        token_hash = self._tokens.hash_refresh_token(refresh_token)
        async with self._uow as uow:
            stored = await uow.refresh_tokens.get_by_hash(token_hash)
            if stored is None or not stored.is_usable(now):
                raise InvalidRefreshToken("Invalid refresh token.")

            if not await uow.refresh_tokens.consume(stored.id, now):
                # Already used, so one of the two holders is a thief: end the whole session.
                # Committed before raising, otherwise the revocation would be rolled back.
                await uow.refresh_tokens.revoke_family(stored.family_id, now)
                await uow.commit()
                raise InvalidRefreshToken("Invalid refresh token.")

            account = await uow.accounts.get(stored.account_id)
            if account is None or not account.is_active:
                await uow.refresh_tokens.revoke_family(stored.family_id, now)
                await uow.commit()
                raise InvalidRefreshToken("Invalid refresh token.")

            pair = await issue_tokens(
                uow,
                self._tokens,
                self._clock,
                account_id=account.id,
                family_id=stored.family_id,
                refresh_ttl_s=self._refresh_ttl_s,
            )
            await uow.commit()
        return pair


class Logout:
    def __init__(self, uow: AccountsUnitOfWork, tokens: TokenService, clock: Clock) -> None:
        self._uow = uow
        self._tokens = tokens
        self._clock = clock

    async def execute(self, refresh_token: str) -> None:
        """Does nothing for an unknown token: the caller is logged out either way."""
        async with self._uow as uow:
            stored = await uow.refresh_tokens.get_by_hash(
                self._tokens.hash_refresh_token(refresh_token)
            )
            if stored is not None:
                await uow.refresh_tokens.revoke(stored.id, self._clock.now())
                await uow.commit()


class LogoutEverywhere:
    def __init__(self, uow: AccountsUnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    async def execute(self, account_id: UUID) -> None:
        async with self._uow as uow:
            await uow.refresh_tokens.revoke_all(account_id, self._clock.now())
            await uow.commit()


class AuthenticateAccount:
    def __init__(self, uow: AccountsUnitOfWork, tokens: TokenService) -> None:
        self._uow = uow
        self._tokens = tokens

    async def execute(self, access_token: str) -> UUID:
        try:
            account_id = self._tokens.verify_access_token(access_token)
        except InvalidAccessToken as error:
            raise Unauthorized("Invalid or expired access token.") from error
        async with self._uow as uow:
            account = await uow.accounts.get(account_id)
        if account is None or not account.is_active:
            raise Unauthorized("Invalid or expired access token.")
        return account.id
