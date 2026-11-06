from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


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
    def now(self) -> datetime: ...
