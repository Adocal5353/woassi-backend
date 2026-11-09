from woassi.modules.messaging.application.ports import (
    Inbox,
    MessageTemplateRepository,
    OutboundMessageRepository,
)
from woassi.modules.messaging.infrastructure.repository import (
    SqlAlchemyInbox,
    SqlAlchemyMessageTemplates,
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

    @property
    def templates(self) -> MessageTemplateRepository:
        return SqlAlchemyMessageTemplates(self._active_session())
