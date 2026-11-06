from arq.connections import ArqRedis

from woassi.shared.domain.events import DomainEvent


class ArqDeferredDispatcher:
    def __init__(self, pool: ArqRedis) -> None:
        self._pool = pool

    async def defer(self, subscriber: str, event: DomainEvent) -> None:
        # arq logs the repr of job arguments: personal data in an event needs repr=False.
        await self._pool.enqueue_job("dispatch_event", subscriber, event)
