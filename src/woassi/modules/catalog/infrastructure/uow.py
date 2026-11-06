from woassi.modules.catalog.application.ports import ProductRepository
from woassi.modules.catalog.infrastructure.repository import SqlAlchemyProductRepository
from woassi.shared.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyCatalogUoW(SqlAlchemyUnitOfWork):
    @property
    def products(self) -> ProductRepository:
        return SqlAlchemyProductRepository(self._active_session(), self._track)
