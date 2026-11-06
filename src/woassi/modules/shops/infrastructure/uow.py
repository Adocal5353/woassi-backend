from woassi.modules.shops.application.ports import ShopRepository
from woassi.modules.shops.infrastructure.repository import SqlAlchemyShopRepository
from woassi.shared.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyShopsUoW(SqlAlchemyUnitOfWork):
    @property
    def shops(self) -> ShopRepository:
        return SqlAlchemyShopRepository(self._active_session(), self._track)
