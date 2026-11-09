from woassi.modules.messaging.application.ports import Inbox, OutboundMessageRepository
from woassi.modules.messaging.infrastructure.repository import (
    SqlAlchemyInbox,
    SqlAlchemyOutboundMessages,
)
from woassi.shared.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyMessagingUoW(SqlAlchemyUnitOfWork):
    @property
    def inbox(self) -> Inbox:
        return SqlAlchemyInbox(self._active_session())

    @property
    def outbound(self) -> OutboundMessageRepository:
        return SqlAlchemyOutboundMessages(self._active_session())
