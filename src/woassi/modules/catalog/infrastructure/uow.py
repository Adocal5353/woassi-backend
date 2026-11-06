from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from woassi.modules.catalog.application.ports import ProductRepository
from woassi.modules.catalog.infrastructure.repository import SqlAlchemyProductRepository


class SqlAlchemyCatalogUoW:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions
        self._session: AsyncSession | None = None

    @property
    def products(self) -> ProductRepository:
        return SqlAlchemyProductRepository(self._active_session())

    async def __aenter__(self) -> Self:
        self._session = self._sessions()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        session = self._active_session()
        self._session = None
        # No-op after a commit; undoes everything else.
        await session.rollback()
        await session.close()

    async def commit(self) -> None:
        await self._active_session().commit()

    async def rollback(self) -> None:
        await self._active_session().rollback()

    def _active_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("Unit of Work used outside `async with`.")
        return self._session
