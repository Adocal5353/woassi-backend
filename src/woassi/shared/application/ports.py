from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Any, Protocol, Self
from uuid import UUID

from woassi.shared.domain.audit import AuditEntry
from woassi.shared.domain.events import DomainEvent
from woassi.shared.domain.values import PhoneNumber


@dataclass(frozen=True, slots=True)
class ObjectInfo:
    key: str
    size: int
    content_type: str | None


class StoragePort(Protocol):
    """Object storage. One instance maps to one bucket."""

    async def presigned_put(self, key: str, content_type: str, expire_s: int = 600) -> str: ...

    async def presigned_get(self, key: str, expire_s: int = 3600) -> str: ...

    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    async def get(self, key: str) -> bytes:
        """Raise ObjectNotFound if the object does not exist."""
        ...

    async def stat(self, key: str) -> ObjectInfo | None: ...

    async def delete(self, key: str) -> None: ...

    def public_url(self, key: str) -> str:
        """Raise an error if the bucket is not public."""
        ...


class Clock(Protocol):
    def now(self) -> datetime:
        """Current time in UTC. Always store this one."""
        ...

    def local_now(self) -> datetime:
        """Current time in Africa/Lome. For display only."""
        ...


class EventBus(Protocol):
    async def publish(self, event: DomainEvent) -> None: ...


class SecretDecryptionError(Exception):
    """A secret cannot be decrypted: wrong key or corrupted value. Not a client error."""


class SecretCipher(Protocol):
    def encrypt(self, plaintext: str) -> str: ...

    def decrypt(self, ciphertext: str) -> str:
        """Raise SecretDecryptionError if `ciphertext` cannot be decrypted."""
        ...


class PhoneNormalizer(Protocol):
    def normalize(self, raw: str) -> PhoneNumber:
        """Raise InvalidData if `raw` is not a valid phone number."""
        ...


class AuditLog(Protocol):
    """Append-only. Writes join the transaction of the action they describe."""

    async def record(
        self,
        *,
        account_id: UUID,
        action: str,
        target_type: str,
        target_id: str,
        shop_id: UUID | None = None,
        details: Mapping[str, Any] | None = None,
        ip: str | None = None,
    ) -> None: ...

    async def list(self, shop_id: UUID, offset: int, limit: int) -> Sequence[AuditEntry]: ...

    async def count(self, shop_id: UUID) -> int: ...


class UnitOfWork(Protocol):
    """One transaction. Events recorded by saved entities are published after the commit."""

    @property
    def audit(self) -> AuditLog: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


@dataclass(frozen=True, slots=True)
class StoredResponse:
    status: int
    content_type: str | None
    body: bytes


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    fingerprint: str
    response: StoredResponse | None  # None while the first request is still running


class IdempotencyStore(Protocol):
    async def begin(self, key: str, fingerprint: str) -> IdempotencyRecord | None:
        """Reserve `key`. Return None if it was free, otherwise the existing record."""
        ...

    async def complete(self, key: str, fingerprint: str, response: StoredResponse) -> None: ...

    async def release(self, key: str) -> None: ...


@dataclass(frozen=True, slots=True)
class AuthenticatedAccount:
    id: UUID


class AccountAuthenticator(Protocol):
    async def authenticate(self, access_token: str) -> AuthenticatedAccount:
        """Raise Unauthorized if the token is invalid or the account cannot be used."""
        ...


class ShopOwnershipPort(Protocol):
    async def owns(self, account_id: UUID, shop_id: UUID) -> bool: ...


class RateLimiter(Protocol):
    async def hit(self, key: str, limit: int, window_s: int) -> int | None:
        """Count one attempt. Return None if allowed, else the seconds left in the window."""
        ...

    async def forgive(self, key: str) -> None:
        """Take back one attempt, for instance when it turned out to be legitimate."""
        ...
