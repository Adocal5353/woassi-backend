from woassi.modules.customers.application.ports import CustomerRepository
from woassi.modules.customers.infrastructure.repository import SqlAlchemyCustomerRepository
from woassi.shared.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyCustomersUoW(SqlAlchemyUnitOfWork):
    @property
    def customers(self) -> CustomerRepository:
        return SqlAlchemyCustomerRepository(self._active_session(), self._track)
