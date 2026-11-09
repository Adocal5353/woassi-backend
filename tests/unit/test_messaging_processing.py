from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tests.fakes import (
    FakeMessagingUoW,
    FakeShopConnections,
    FakeTemplateRegistry,
    FakeWhatsAppAccounts,
    MessagingState,
    RecordingInboundHandler,
)
from woassi.modules.messaging.application.ports import SendError, SendFailure, ShopConnection
from woassi.modules.messaging.application.use_cases.processing import HandleMetaEvent
from woassi.modules.messaging.application.use_cases.sending import SendWhatsAppMessage
from woassi.modules.messaging.application.use_cases.templates import EnsureTemplateSendable
from woassi.modules.messaging.domain.content import MessageContent, Recipient, TextMessage
from woassi.modules.messaging.domain.errors import (
    InvalidRecipient,
    MessageNotSent,
    OutsideCustomerServiceWindow,
    ShopNotConnected,
)
from woassi.modules.messaging.domain.event import (
    AccountUpdate,
    InboundMessage,
    MessageStatusUpdate,
)
from woassi.modules.messaging.domain.outbound import OutboundStatus
from woassi.shared.infrastructure.clock import FrozenClock

SHOP = ShopConnection(shop_id=uuid4(), waba_id="1001", phone_number_id="2002", access_token="token")
CLOCK = FrozenClock(datetime(2026, 1, 1, tzinfo=UTC))


def message(message_id: str = "wamid.1", phone_number_id: str = "2002") -> InboundMessage:
    return InboundMessage(
        phone_number_id=phone_number_id, message_id=message_id, type="order", sender_user_id="TG.1"
    )


class Stack:
    def __init__(self, handler: RecordingInboundHandler | None = None) -> None:
        self.database = MessagingState()
        self.handler = handler or RecordingInboundHandler()
        self.accounts = FakeWhatsAppAccounts()

    def handle(self) -> HandleMetaEvent:
        return HandleMetaEvent(
            FakeMessagingUoW(self.database),
            FakeShopConnections(SHOP),
            self.accounts,
            self.handler,
            CLOCK,
        )


async def test_a_message_reaches_its_shop() -> None:
    stack = Stack()
    await stack.handle().execute(message())
    assert stack.handler.handled == [(SHOP.shop_id, message())]


async def test_a_duplicate_is_handled_once() -> None:
    """Meta resends webhooks, and a retried job may run twice."""
    stack = Stack()
    await stack.handle().execute(message())
    await stack.handle().execute(message())
    assert len(stack.handler.handled) == 1


async def test_a_failed_handling_is_retried_later() -> None:
    stack = Stack(RecordingInboundHandler(failures=1))
    with pytest.raises(ConnectionError):
        await stack.handle().execute(message())

    await stack.handle().execute(message())

    assert len(stack.handler.handled) == 1


async def test_a_message_for_an_unknown_number_is_dropped_once() -> None:
    stack = Stack()
    await stack.handle().execute(message(phone_number_id="999"))
    assert stack.handler.handled == []
    assert ("meta.message", "wamid.1") in stack.database.claimed


async def test_losing_access_to_an_account_releases_its_shops() -> None:
    stack = Stack()
    for event in ("PARTNER_REMOVED", "ACCOUNT_DELETED", "ACCOUNT_OFFBOARDED"):
        await stack.handle().execute(AccountUpdate(waba_id="1001", event=event))
    assert stack.accounts.removed == ["1001", "1001", "1001"]


@pytest.mark.parametrize("event", ["PARTNER_ADDED", "ACCOUNT_RECONNECTED", "ACCOUNT_VIOLATION"])
async def test_other_account_events_change_nothing(event: str) -> None:
    stack = Stack()
    await stack.handle().execute(AccountUpdate(waba_id="1001", event=event))
    assert stack.accounts.removed == []


class FakeSender:
    def __init__(self, error: SendError | None = None) -> None:
        self.error = error
        self.sent: list[tuple[ShopConnection, Recipient, MessageContent]] = []

    async def send(
        self, connection: ShopConnection, recipient: Recipient, content: MessageContent
    ) -> str:
        if self.error:
            raise self.error
        self.sent.append((connection, recipient, content))
        return f"wamid.{len(self.sent)}"


def sending(database: MessagingState, sender: FakeSender) -> SendWhatsAppMessage:
    uow = FakeMessagingUoW(database)
    guard = EnsureTemplateSendable(uow, FakeTemplateRegistry(), CLOCK)
    return SendWhatsAppMessage(uow, FakeShopConnections(SHOP), sender, guard, CLOCK)


async def send(database: MessagingState, sender: FakeSender, shop_id: object = None) -> str:
    return await sending(database, sender).execute(
        shop_id=shop_id or SHOP.shop_id,  # type: ignore[arg-type]
        recipient=Recipient(user_id="TG.1"),
        content=TextMessage("Bonjour"),
        kind="test",
    )


async def test_sending_records_the_message() -> None:
    database, sender = MessagingState(), FakeSender()
    message_id = await send(database, sender)

    stored = database.outbound[message_id]
    assert (stored.shop_id, stored.recipient, stored.kind) == (SHOP.shop_id, "TG.1", "test")
    assert stored.status is OutboundStatus.ACCEPTED
    assert sender.sent[0][0] == SHOP


async def test_sending_needs_a_connected_shop() -> None:
    with pytest.raises(ShopNotConnected):
        await send(MessagingState(), FakeSender(), shop_id=uuid4())


@pytest.mark.parametrize(
    ("failure", "error"),
    [
        (SendFailure.OUTSIDE_WINDOW, OutsideCustomerServiceWindow),
        (SendFailure.INVALID_RECIPIENT, InvalidRecipient),
        (SendFailure.RATE_LIMITED, MessageNotSent),
        (SendFailure.INVALID_TOKEN, MessageNotSent),
        (SendFailure.UNAVAILABLE, MessageNotSent),
    ],
)
async def test_send_failures(failure: SendFailure, error: type[Exception]) -> None:
    database = MessagingState()
    with pytest.raises(error):
        await send(database, FakeSender(SendError(failure, meta_code=1)))
    assert database.outbound == {}


async def test_status_webhooks_update_the_record() -> None:
    database, stack = MessagingState(), Stack()
    stack.database = database
    message_id = await send(database, FakeSender())

    for status in ("delivered", "sent", "read"):
        await stack.handle().execute(MessageStatusUpdate("2002", message_id, status))

    assert database.outbound[message_id].status is OutboundStatus.READ


async def test_a_failure_status_keeps_its_code() -> None:
    database, stack = MessagingState(), Stack()
    stack.database = database
    message_id = await send(database, FakeSender())

    await stack.handle().execute(
        MessageStatusUpdate("2002", message_id, "failed", error_codes=(131049,))
    )

    assert database.outbound[message_id].status is OutboundStatus.FAILED
    assert database.outbound[message_id].error_code == 131049


async def test_status_of_a_message_sent_elsewhere_is_ignored() -> None:
    stack = Stack()
    await stack.handle().execute(MessageStatusUpdate("2002", "wamid.from-the-app", "read"))
    await stack.handle().execute(MessageStatusUpdate("2002", "wamid.x", "deleted"))
    assert stack.database.outbound == {}
