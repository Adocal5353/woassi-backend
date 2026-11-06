import base64
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

from arq.connections import ArqRedis
from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from woassi.shared.application.ports import IdempotencyRecord, StoredResponse
from woassi.shared.infrastructure.db.base import Base

RESPONSE_TTL_S = 24 * 3600
# Bounds how long a crashed request blocks its key.
PENDING_TTL_S = 300


class ProcessedKeyModel(Base):
    __tablename__ = "processed_keys"

    source: Mapped[str] = mapped_column(String(50), primary_key=True)
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


@asynccontextmanager
async def process_once(session: AsyncSession, source: str, key: str) -> AsyncIterator[bool]:
    """Yield True the first time (source, key) is seen, False afterwards.

    The key joins the caller's transaction, which still has to commit. If the block raises, its
    savepoint is rolled back and the key is released, so the event can be retried. A concurrent
    duplicate waits on the unique key until the first transaction ends.
    """
    async with session.begin_nested():
        result = await session.execute(
            insert(ProcessedKeyModel)
            .values(source=source, key=key)
            .on_conflict_do_nothing()
            .returning(ProcessedKeyModel.key)
        )
        yield result.first() is not None


def _dump(fingerprint: str, response: StoredResponse | None) -> str:
    stored = None
    if response is not None:
        stored = {
            "status": response.status,
            "content_type": response.content_type,
            "body": base64.b64encode(response.body).decode(),
        }
    return json.dumps({"fingerprint": fingerprint, "response": stored})


def _load(raw: bytes) -> IdempotencyRecord:
    data = json.loads(raw)
    stored = data["response"]
    response = None
    if stored is not None:
        response = StoredResponse(
            status=stored["status"],
            content_type=stored["content_type"],
            body=base64.b64decode(stored["body"]),
        )
    return IdempotencyRecord(fingerprint=data["fingerprint"], response=response)


class RedisIdempotencyStore:
    def __init__(self, redis: ArqRedis) -> None:
        self._redis = redis

    async def begin(self, key: str, fingerprint: str) -> IdempotencyRecord | None:
        reserved = await self._redis.set(
            self._name(key), _dump(fingerprint, None), nx=True, ex=PENDING_TTL_S
        )
        if reserved:
            return None
        raw = await self._redis.get(self._name(key))
        if raw is None:  # expired between the two calls
            return await self.begin(key, fingerprint)
        return _load(raw)

    async def complete(self, key: str, fingerprint: str, response: StoredResponse) -> None:
        await self._redis.set(self._name(key), _dump(fingerprint, response), ex=RESPONSE_TTL_S)

    async def release(self, key: str) -> None:
        await self._redis.delete(self._name(key))

    @staticmethod
    def _name(key: str) -> str:
        return f"idempotency:{key}"
