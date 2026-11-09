from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Protocol
from uuid import UUID

from woassi.modules.messaging.domain.content import MessageContent, Recipient
from woassi.modules.messaging.domain.event import InboundMessage, MetaEvent
from woassi.modules.messaging.domain.outbound import OutboundMessage
from woassi.shared.application.ports import UnitOfWork


class EventQueue(Protocol):
    async def enqueue(self, event: MetaEvent) -> None: ...


@dataclass(frozen=True, slots=True)
class ShopConnection:
    shop_id: UUID
    phone_number_id: str
    access_token: str = field(repr=False)


class ShopConnectionsPort(Protocol):
    """None for an unknown shop or number, or a shop that may not process messages."""

    async def by_phone_number_id(self, phone_number_id: str) -> ShopConnection | None: ...

    async def by_shop_id(self, shop_id: UUID) -> ShopConnection | None: ...


class WhatsAppAccountsPort(Protocol):
    async def account_removed(self, waba_id: str) -> int:
        """Woassi lost access to this account. Return how many shops it affected."""
        ...


class InboundMessageHandler(Protocol):
    async def handle(self, shop_id: UUID, message: InboundMessage) -> None:
        """Raise to have the message retried: its key is only kept if this returns."""
        ...


class Inbox(Protocol):
    async def claim(self, source: str, key: str) -> bool:
        """Reserve the key in the current transaction. False if already processed."""
        ...


class OutboundMessageRepository(Protocol):
    async def add(self, message: OutboundMessage) -> None: ...

    async def get(self, message_id: str) -> OutboundMessage | None: ...

    async def save(self, message: OutboundMessage) -> None: ...


class MessagingUnitOfWork(UnitOfWork, Protocol):
    @property
    def inbox(self) -> Inbox: ...

    @property
    def outbound(self) -> OutboundMessageRepository: ...


class SendFailure(Enum):
    OUTSIDE_WINDOW = auto()
    RATE_LIMITED = auto()
    INVALID_RECIPIENT = auto()
    INVALID_TOKEN = auto()
    UNAVAILABLE = auto()
    REJECTED = auto()


class SendError(Exception):
    """Carries no text from Meta on purpose: it is safe to log."""

    def __init__(self, failure: SendFailure, *, meta_code: int | None = None) -> None:
        super().__init__(f"{failure.name} (Meta code {meta_code})")
        self.failure = failure
        self.meta_code = meta_code


class WhatsAppSender(Protocol):
    async def send(
        self, connection: ShopConnection, recipient: Recipient, content: MessageContent
    ) -> str:
        """Return Meta's message id. Raise SendError otherwise."""
        ...
