from dataclasses import dataclass

import pytest
from arq import Worker, func
from arq.connections import ArqRedis

from woassi.shared.application.ports import IdempotencyRecord, StoredResponse
from woassi.shared.domain.events import DomainEvent
from woassi.shared.infrastructure.events.arq_dispatcher import ArqDeferredDispatcher
from woassi.shared.infrastructure.events.bus import InProcessEventBus
from woassi.shared.infrastructure.idempotency import (
    PENDING_TTL_S,
    RESPONSE_TTL_S,
    RedisIdempotencyStore,
)

pytestmark = pytest.mark.integration


@dataclass(frozen=True, kw_only=True)
class SomethingHappened(DomainEvent):
    what: str


RESPONSE = StoredResponse(status=201, content_type="application/json", body=b'{"id": 1}\xff')


async def test_begin_reserves_the_key_once(pool: ArqRedis) -> None:
    store = RedisIdempotencyStore(pool)

    assert await store.begin("k", "fingerprint") is None
    assert await store.begin("k", "fingerprint") == IdempotencyRecord("fingerprint", None)
    assert 0 < await pool.ttl("idempotency:k") <= PENDING_TTL_S


async def test_a_completed_response_is_kept_for_24_hours(pool: ArqRedis) -> None:
    store = RedisIdempotencyStore(pool)
    await store.begin("k", "fingerprint")

    await store.complete("k", "fingerprint", RESPONSE)

    assert await store.begin("k", "fingerprint") == IdempotencyRecord("fingerprint", RESPONSE)
    assert PENDING_TTL_S < await pool.ttl("idempotency:k") <= RESPONSE_TTL_S


async def test_release_frees_the_key(pool: ArqRedis) -> None:
    store = RedisIdempotencyStore(pool)
    await store.begin("k", "fingerprint")

    await store.release("k")

    assert await store.begin("k", "fingerprint") is None


async def test_deferred_subscriber_runs_through_arq(pool: ArqRedis) -> None:
    received: list[DomainEvent] = []

    async def handler(event: SomethingHappened) -> None:
        received.append(event)

    bus = InProcessEventBus(ArqDeferredDispatcher(pool))
    bus.subscribe(SomethingHappened, handler, name="later", deferred=True)

    async def dispatch_event(ctx: dict[str, object], subscriber: str, event: DomainEvent) -> None:
        await bus.dispatch(subscriber, event)

    event = SomethingHappened(what="x")
    await bus.publish(event)
    assert received == []

    worker = Worker(
        functions=[func(dispatch_event, name="dispatch_event")], redis_pool=pool, burst=True
    )
    await worker.main()
    await worker.close()

    assert received == [event]
