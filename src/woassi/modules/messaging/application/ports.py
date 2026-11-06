from typing import Protocol

from woassi.modules.messaging.domain.event import MetaEvent


class EventQueue(Protocol):
    async def enqueue(self, event: MetaEvent) -> None: ...
