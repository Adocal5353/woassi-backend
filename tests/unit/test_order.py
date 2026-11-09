from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from woassi.modules.orders.domain.errors import OrderNotOpen
from woassi.modules.orders.domain.events import OrderClosed, OrderConfirmed
from woassi.modules.orders.domain.order import (
    ClosingReason,
    Deadlines,
    DecidedBy,
    DueAction,
    Order,
    OrderLine,
    OrderStatus,
    ValidationMode,
    ValidationPolicy,
)
from woassi.shared.domain.values import Amount

NOW = datetime(2026, 1, 1, 9, tzinfo=UTC)
MANUAL = ValidationPolicy(ValidationMode.MANUAL)
AUTOMATIC = ValidationPolicy(ValidationMode.AUTOMATIC)


def line(requested: int, quantity: int, price: int = 5000, name: str = "Pagne") -> OrderLine:
    return OrderLine(
        retailer_id=name,
        name=name,
        unit_price=Amount(price),
        requested=requested,
        quantity=quantity,
        product_id=uuid4(),
    )


def order(*lines: OrderLine, policy: ValidationPolicy = MANUAL) -> Order:
    return Order.receive(
        shop_id=uuid4(),
        number=1,
        customer_id=uuid4(),
        source_message_id="wamid.1",
        lines=lines,
        note="",
        policy=policy,
        deadlines=Deadlines(),
        now=NOW,
    )


def test_total_counts_what_is_reserved() -> None:
    assert order(line(2, 2), line(1, 1, price=12500)).total == Amount(22500)


def test_manual_mode_waits_for_the_merchant() -> None:
    received = order(line(2, 2))
    assert received.status is OrderStatus.AWAITING_MERCHANT
    assert received.next_reminder_at == NOW + timedelta(minutes=15)
    assert received.expires_at == NOW + timedelta(hours=24)


def test_automatic_mode_confirms_a_complete_cart() -> None:
    received = order(line(2, 2), policy=AUTOMATIC)
    assert received.status is OrderStatus.CONFIRMED
    assert received.decided_by is DecidedBy.AUTOMATIC
    assert received.next_deadline is None
    [event] = received.pull_events()
    assert isinstance(event, OrderConfirmed) and event.total == 10000


def test_automatic_mode_sends_big_orders_to_the_merchant() -> None:
    policy = ValidationPolicy(ValidationMode.AUTOMATIC, max_amount=Amount(9999))
    assert order(line(2, 2), policy=policy).status is OrderStatus.AWAITING_MERCHANT
    assert order(line(1, 1), policy=policy).status is OrderStatus.CONFIRMED


def test_a_partial_cart_asks_the_customer_first_even_in_automatic_mode() -> None:
    received = order(line(3, 1), line(1, 1), policy=AUTOMATIC)
    assert received.status is OrderStatus.AWAITING_CUSTOMER
    assert received.total == Amount(10000)
    assert [m.requested - m.quantity for m in received.missing_lines] == [2]


def test_nothing_available_is_rejected() -> None:
    received = order(line(2, 0))
    assert received.status is OrderStatus.REJECTED
    assert received.closing_reason is ClosingReason.OUT_OF_STOCK
    assert received.reserved == {}
    assert isinstance(received.pull_events()[0], OrderClosed)


def test_accepting_the_offer_keeps_what_is_available() -> None:
    received = order(line(3, 1), line(1, 0, name="Sac"))
    received.accept_offer(MANUAL, NOW)
    assert received.status is OrderStatus.AWAITING_MERCHANT
    assert [(x.name, x.requested, x.quantity) for x in received.lines] == [("Pagne", 1, 1)]


def test_declining_the_offer_cancels() -> None:
    received = order(line(3, 1))
    received.decline_offer(NOW)
    assert received.status is OrderStatus.CANCELLED
    assert received.closing_reason is ClosingReason.CUSTOMER_DECLINED
    assert sum(received.reserved.values()) == 1  # still to give back


def test_merchant_decisions() -> None:
    accepted, refused = order(line(1, 1)), order(line(1, 1))
    accepted.confirm(NOW)
    refused.refuse(NOW)
    assert accepted.status is OrderStatus.CONFIRMED
    assert accepted.decided_by is DecidedBy.MERCHANT
    assert refused.closing_reason is ClosingReason.MERCHANT_REFUSED


@pytest.mark.parametrize("step", ["confirm", "refuse", "accept_offer", "decline_offer", "expire"])
def test_a_closed_order_does_not_move(step: str) -> None:
    closed = order(line(1, 1))
    closed.confirm(NOW)
    with pytest.raises(OrderNotOpen):
        if step == "accept_offer":
            closed.accept_offer(MANUAL, NOW)
        else:
            getattr(closed, step)(NOW)


def test_the_merchant_cannot_decide_while_the_customer_has_not() -> None:
    with pytest.raises(OrderNotOpen):
        order(line(3, 1)).confirm(NOW)


def test_reminders_then_expiry() -> None:
    waiting = order(line(1, 1))
    assert waiting.due_action(NOW + timedelta(minutes=14)) is None
    assert waiting.due_action(NOW + timedelta(minutes=15)) is DueAction.REMIND

    waiting.reminded()
    assert waiting.next_reminder_at == NOW + timedelta(minutes=60)
    waiting.reminded()
    assert waiting.next_reminder_at is None
    assert waiting.next_deadline == waiting.expires_at

    assert waiting.due_action(NOW + timedelta(hours=23)) is None
    assert waiting.due_action(NOW + timedelta(hours=24)) is DueAction.EXPIRE
    waiting.expire(NOW + timedelta(hours=24))
    assert waiting.status is OrderStatus.EXPIRED
    assert waiting.due_action(NOW + timedelta(hours=48)) is None


def test_a_waiting_customer_gets_no_reminder_but_expires() -> None:
    offered = order(line(3, 1))
    assert offered.next_reminder_at is None
    assert offered.due_action(NOW + timedelta(hours=24)) is DueAction.EXPIRE


def test_reminders_count_from_when_the_merchant_was_asked() -> None:
    offered = order(line(3, 1))
    later = NOW + timedelta(hours=2)
    offered.accept_offer(MANUAL, later)
    assert offered.next_reminder_at == later + timedelta(minutes=15)
    offered.reminded()
    assert offered.next_reminder_at == later + timedelta(minutes=60)


def test_personal_data_stays_out_of_repr() -> None:
    noted = Order.receive(
        shop_id=uuid4(),
        number=1,
        customer_id=uuid4(),
        source_message_id="m",
        lines=(line(1, 1),),
        note="Livraison à Bè",
        policy=MANUAL,
        deadlines=Deadlines(),
        now=NOW,
    )
    assert "Bè" not in repr(noted)
