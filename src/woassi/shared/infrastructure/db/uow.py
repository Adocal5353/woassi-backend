from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from woassi.shared.application.ports import AuditLog, Clock, EventBus
from woassi.shared.domain.events import DomainEvent, Entity
from woassi.shared.infrastructure.audit import SqlAlchemyAuditLog


class SqlAlchemyUnitOfWork:
    """Repositories call `_track` on saved entities; their events go out after the commit."""

    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], event_bus: EventBus, clock: Clock
    ) -> None:
        self._sessions = sessions
        self._event_bus = event_bus
        self._clock = clock
        self._session: AsyncSession | None = None
        self._tracked: list[Entity] = []

    @property
    def audit(self) -> AuditLog:
        return SqlAlchemyAuditLog(self._active_session(), self._clock)

    async def __aenter__(self) -> Self:
        self._session = self._sessions()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        # No-op after a commit; undoes everything else.
        await self.rollback()
        session = self._active_session()
        self._session = None
        await session.close()

    async def commit(self) -> None:
        await self._active_session().commit()
        for event in self._pull_events():
            await self._event_bus.publish(event)

    async def rollback(self) -> None:
        await self._active_session().rollback()
        self._pull_events()

    def _track(self, entity: Entity) -> None:
        self._tracked.append(entity)

    def _pull_events(self) -> list[DomainEvent]:
        events = [event for entity in self._tracked for event in entity.pull_events()]
        self._tracked.clear()
        return events

    def _active_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("Unit of Work used outside `async with`.")
        return self._session
