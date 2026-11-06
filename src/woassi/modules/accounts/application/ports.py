from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from woassi.modules.accounts.domain.account import Account
from woassi.modules.accounts.domain.refresh_token import RefreshToken
from woassi.modules.accounts.domain.verification_code import CodePurpose, VerificationCode
from woassi.shared.application.ports import UnitOfWork
from woassi.shared.domain.values import PhoneNumber


class AccountRepository(Protocol):
    async def add(self, account: Account) -> None:
        """Raise PhoneAlreadyUsed if the phone number is taken."""
        ...

    async def get(self, account_id: UUID) -> Account | None: ...

    async def get_by_phone(self, phone: PhoneNumber) -> Account | None: ...

    async def save(self, account: Account) -> None: ...


class RefreshTokenStore(Protocol):
    async def add(self, token: RefreshToken) -> None: ...

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None: ...

    async def consume(self, token_id: UUID, now: datetime) -> bool:
        """Atomically mark the token as consumed. False if something got there first."""
        ...

    async def revoke(self, token_id: UUID, now: datetime) -> None: ...

    async def revoke_family(self, family_id: UUID, now: datetime) -> None: ...

    async def revoke_all(self, account_id: UUID, now: datetime) -> None: ...


class VerificationCodeStore(Protocol):
    async def add(self, code: VerificationCode) -> None: ...

    async def get_latest(self, account_id: UUID, purpose: CodePurpose) -> VerificationCode | None:
        """Lock and return the latest code, so that concurrent attempts are all counted."""
        ...

    async def save(self, code: VerificationCode) -> None: ...

    async def invalidate(self, account_id: UUID, purpose: CodePurpose, now: datetime) -> None: ...


class AccountsUnitOfWork(UnitOfWork, Protocol):
    @property
    def accounts(self) -> AccountRepository: ...

    @property
    def refresh_tokens(self) -> RefreshTokenStore: ...

    @property
    def verification_codes(self) -> VerificationCodeStore: ...


class PasswordHasher(Protocol):
    async def hash(self, password: str) -> str: ...

    async def verify(self, password: str, password_hash: str) -> bool: ...

    async def dummy_verify(self, password: str) -> None:
        """Take as long as `verify`, so that an unknown phone number cannot be timed."""
        ...


class InvalidAccessToken(Exception):
    pass


@dataclass(frozen=True, slots=True)
class AccessToken:
    token: str = field(repr=False)
    expires_in: int


class TokenService(Protocol):
    def issue_access_token(self, account_id: UUID) -> AccessToken: ...

    def verify_access_token(self, token: str) -> UUID:
        """Return the account id. Raise InvalidAccessToken otherwise."""
        ...

    def new_refresh_token(self) -> str: ...

    def hash_refresh_token(self, token: str) -> str: ...


class VerificationCodeSender(Protocol):
    async def send(self, phone: PhoneNumber, code: str, purpose: CodePurpose) -> None: ...
