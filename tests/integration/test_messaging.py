import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.fakes import FakeShopConnections, FakeWhatsAppAccounts, RecordingInboundHandler
from woassi.modules.messaging.application.ports import ShopConnection
from woassi.modules.messaging.application.use_cases.processing import HandleMetaEvent
from woassi.modules.messaging.domain.event import InboundMessage, MessageStatusUpdate
from woassi.modules.messaging.domain.outbound import OutboundMessage, OutboundStatus
from woassi.modules.messaging.infrastructure.uow import SqlAlchemyMessagingUoW
from woassi.shared.domain.events import DomainEvent
from woassi.shared.infrastructure.clock import FrozenClock

pytestmark = pytest.mark.integration

CLOCK = FrozenClock(datetime(2026, 1, 1, tzinfo=UTC))
SHOP = ShopConnection(shop_id=uuid4(), waba_id="1001", phone_number_id="2002", access_token="token")
MESSAGE = InboundMessage(
    phone_number_id="2002", message_id="wamid.1", type="order", sender_user_id="TG.1"
)


class NullBus:
    async def publish(self, event: DomainEvent) -> None:
        return None


def uow(sessions: async_sessionmaker[AsyncSession]) -> SqlAlchemyMessagingUoW:
    return SqlAlchemyMessagingUoW(sessions, NullBus(), CLOCK)


class SlowHandler(RecordingInboundHandler):
    async def handle(self, shop_id: object, message: InboundMessage) -> None:  # type: ignore[override]
        await asyncio.sleep(0.05)
        await super().handle(shop_id, message)  # type: ignore[arg-type]


def handling(
    sessions: async_sessionmaker[AsyncSession], handler: RecordingInboundHandler
) -> HandleMetaEvent:
    return HandleMetaEvent(
        uow(sessions), FakeShopConnections(SHOP), FakeWhatsAppAccounts(), handler, CLOCK
    )


async def test_concurrent_duplicates_are_handled_once(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Two workers get the same message: the second waits on the key, then skips it."""
    handler = SlowHandler()
    await asyncio.gather(*(handling(sessions, handler).execute(MESSAGE) for _ in range(5)))
    assert len(handler.handled) == 1


async def test_a_failed_handling_leaves_the_key_free(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    handler = RecordingInboundHandler(failures=1)
    with pytest.raises(ConnectionError):
        await handling(sessions, handler).execute(MESSAGE)

    await handling(sessions, handler).execute(MESSAGE)

    assert len(handler.handled) == 1


async def test_outbound_statuses_on_postgres(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with uow(sessions) as unit:
        await unit.outbound.add(
            OutboundMessage(
                id="wamid.OUT",
                shop_id=SHOP.shop_id,
                recipient="TG.1",
                kind="test",
                created_at=CLOCK.now(),
            )
        )
        await unit.commit()

    updates = [
        MessageStatusUpdate("2002", "wamid.OUT", status)
        for status in ("read", "sent", "delivered", "delivered")
    ]
    await asyncio.gather(
        *(handling(sessions, RecordingInboundHandler()).execute(update) for update in updates)
    )

    async with uow(sessions) as unit:
        stored = await unit.outbound.get("wamid.OUT")
    assert stored is not None
    assert stored.status is OutboundStatus.READ
