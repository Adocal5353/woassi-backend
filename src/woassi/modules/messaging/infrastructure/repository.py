from sqlalchemy.ext.asyncio import AsyncSession

from woassi.modules.messaging.domain.outbound import OutboundMessage, OutboundStatus
from woassi.modules.messaging.infrastructure.models import OutboundMessageModel
from woassi.shared.infrastructure.idempotency import claim_key


class SqlAlchemyInbox:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(self, source: str, key: str) -> bool:
        return await claim_key(self._session, source, key)


def _copy(message: OutboundMessage, model: OutboundMessageModel) -> OutboundMessageModel:
    model.id = message.id
    model.shop_id = message.shop_id
    model.recipient = message.recipient
    model.kind = message.kind
    model.status = message.status.value
    model.error_code = message.error_code
    model.created_at = message.created_at
    model.updated_at = message.updated_at
    return model


class SqlAlchemyOutboundMessages:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, message: OutboundMessage) -> None:
        self._session.add(_copy(message, OutboundMessageModel()))
        await self._session.flush()

    async def get(self, message_id: str) -> OutboundMessage | None:
        # Locked: two status webhooks for one message are applied one after the other.
        model = await self._session.get(OutboundMessageModel, message_id, with_for_update=True)
        if model is None:
            return None
        return OutboundMessage(
            id=model.id,
            shop_id=model.shop_id,
            recipient=model.recipient,
            kind=model.kind,
            created_at=model.created_at,
            status=OutboundStatus(model.status),
            error_code=model.error_code,
            updated_at=model.updated_at,
        )

    async def save(self, message: OutboundMessage) -> None:
        model = await self._session.get(OutboundMessageModel, message.id)
        if model is None:
            raise LookupError(f"Outbound message {message.id} does not exist.")
        _copy(message, model)
        await self._session.flush()
