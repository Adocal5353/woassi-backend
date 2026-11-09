from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

from woassi.modules.customers.application.use_cases.customers import (
    ChangeCustomerUserId,
    RecordContact,
)
from woassi.modules.messaging.domain.event import InboundMessage
from woassi.modules.orders.application.use_cases.orders import Cart, ReceiveCart, ReplyToOrder
from woassi.shared.application.ports import Clock
from woassi.shared.domain.errors import InvalidData
from woassi.shared.domain.values import PhoneNumber

log = structlog.get_logger()

MAX_CART_LINES = 100


def _phone(raw: str | None) -> PhoneNumber | None:
    if not raw:
        return None
    try:
        return PhoneNumber(raw if raw.startswith("+") else f"+{raw}")
    except InvalidData:
        return None


def _cart_items(payload: Mapping[str, Any]) -> tuple[tuple[str, int], ...]:
    items = []
    for item in payload.get("product_items") or []:
        if not isinstance(item, Mapping):
            continue
        retailer_id, quantity = item.get("product_retailer_id"), item.get("quantity")
        if isinstance(retailer_id, str) and retailer_id and isinstance(quantity, int):
            items.append((retailer_id[:100], quantity))
    return tuple(items[:MAX_CART_LINES])


def _reply_payload(message: InboundMessage) -> str | None:
    """Quick reply of a template (`button`), or reply button of a free-form message."""
    if message.type == "button":
        payload = message.payload.get("payload")
    elif message.type == "interactive":
        reply = message.payload.get("button_reply")
        payload = reply.get("id") if isinstance(reply, Mapping) else None
    else:
        payload = None
    return payload if isinstance(payload, str) else None


class OrdersInboundHandler:
    """InboundMessageHandler: what a customer or a merchant sends to a shop's number."""

    def __init__(
        self,
        record_contact: RecordContact,
        change_user_id: ChangeCustomerUserId,
        receive_cart: ReceiveCart,
        reply_to_order: ReplyToOrder,
        clock: Clock,
    ) -> None:
        self._record_contact = record_contact
        self._change_user_id = change_user_id
        self._receive_cart = receive_cart
        self._reply_to_order = reply_to_order
        self._clock = clock

    async def handle(self, shop_id: UUID, message: InboundMessage) -> None:
        if message.type == "system":
            await self._system(shop_id, message)
            return

        payload = _reply_payload(message)
        if payload is not None:
            handled = await self._reply_to_order.execute(
                shop_id=shop_id, payload=payload, context_message_id=message.context_message_id
            )
            if handled:
                return

        # Anything else comes from a customer: keep their record, which also tracks the
        # 24-hour window, up to date.
        customer_id = await self._record_contact.execute(
            shop_id=shop_id,
            user_id=message.sender_user_id,
            phone=_phone(message.sender_phone),
            name=message.profile_name,
            at=self._sent_at(message),
        )
        if message.type == "order":
            items = _cart_items(message.payload)
            if not items:
                return
            note = message.payload.get("text")
            await self._receive_cart.execute(
                shop_id=shop_id,
                cart=Cart(
                    message_id=message.message_id,
                    customer_id=customer_id,
                    items=items,
                    note=note[:1000] if isinstance(note, str) else "",
                ),
            )
        else:
            log.info(
                "inbound_message_not_an_order",
                shop_id=str(shop_id),
                message_id=message.message_id,
                type=message.type,
            )

    async def _system(self, shop_id: UUID, message: InboundMessage) -> None:
        previous, current = message.payload.get("previous_user_id"), message.payload.get("user_id")
        if isinstance(previous, str) and isinstance(current, str) and previous != current:
            await self._change_user_id.execute(
                shop_id=shop_id, previous_user_id=previous, user_id=current
            )

    def _sent_at(self, message: InboundMessage) -> datetime:
        if message.timestamp:
            return datetime.fromtimestamp(message.timestamp, UTC)
        return self._clock.now()
