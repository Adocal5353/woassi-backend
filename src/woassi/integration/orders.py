from uuid import UUID

import structlog

from woassi.modules.messaging.domain.event import InboundMessage

log = structlog.get_logger()


class UnhandledInboundMessages:
    """InboundMessageHandler until the orders module exists: messages are only logged.

    TODO(orders): replace with an implementation backed by the orders and customers modules.
    """

    async def handle(self, shop_id: UUID, message: InboundMessage) -> None:
        log.info(
            "inbound_message_unhandled",
            shop_id=str(shop_id),
            message_id=message.message_id,
            type=message.type,
        )
