from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Protocol
from uuid import UUID

from woassi.modules.messaging.domain.content import MessageContent, Recipient
from woassi.modules.messaging.domain.event import InboundMessage, MetaEvent
from woassi.modules.messaging.domain.outbound import OutboundMessage
from woassi.modules.messaging.domain.templates import MessageTemplate, TemplateDefinition
from woassi.shared.application.ports import UnitOfWork


class EventQueue(Protocol):
    async def enqueue(self, event: MetaEvent) -> None: ...


@dataclass(frozen=True, slots=True)
class ShopConnection:
    shop_id: UUID
    waba_id: str
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


class MessageTemplateRepository(Protocol):
    async def get(self, shop_id: UUID, name: str, language: str) -> MessageTemplate | None: ...

    async def list_by_waba(self, waba_id: str, name: str) -> Sequence[MessageTemplate]: ...

    async def save(self, template: MessageTemplate) -> None:
        """Insert or update."""
        ...


class MessagingUnitOfWork(UnitOfWork, Protocol):
    @property
    def inbox(self) -> Inbox: ...

    @property
    def outbound(self) -> OutboundMessageRepository: ...

    @property
    def templates(self) -> MessageTemplateRepository: ...


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


@dataclass(frozen=True, slots=True)
class SubmittedTemplate:
    meta_template_id: str | None
    status: str  # as Meta writes it


class TemplateRegistry(Protocol):
    """Raise SendError on failure."""

    async def submit(
        self, connection: ShopConnection, definition: TemplateDefinition
    ) -> SubmittedTemplate:
        """Create the template, or return the existing one if it is already there."""
        ...

    async def status(
        self, connection: ShopConnection, name: str, language: str
    ) -> SubmittedTemplate | None: ...
