from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from woassi.modules.orders.api.deps import OrdersDep
from woassi.modules.orders.domain.order import (
    ClosingReason,
    DecidedBy,
    Order,
    OrderLine,
    OrderStatus,
)
from woassi.shared.api.deps import CurrentAccount, client_ip, get_authorized_shop
from woassi.shared.api.pagination import Limit, Offset, Page

router = APIRouter(
    prefix="/shops/{shop_id}/orders",
    tags=["orders"],
    dependencies=[Depends(get_authorized_shop)],
)


class OrderLineResponse(BaseModel):
    retailer_id: str
    product_id: UUID | None
    name: str
    unit_price: int
    requested: int
    quantity: int
    subtotal: int

    @classmethod
    def from_line(cls, line: OrderLine) -> "OrderLineResponse":
        return cls(
            retailer_id=line.retailer_id,
            product_id=line.product_id,
            name=line.name,
            unit_price=line.unit_price.value,
            requested=line.requested,
            quantity=line.quantity,
            subtotal=line.subtotal.value,
        )


class OrderResponse(BaseModel):
    id: UUID
    number: int
    customer_id: UUID
    status: OrderStatus
    lines: list[OrderLineResponse]
    total: int
    note: str
    created_at: datetime
    expires_at: datetime
    closed_at: datetime | None
    closing_reason: ClosingReason | None
    decided_by: DecidedBy | None

    @classmethod
    def from_order(cls, order: Order) -> "OrderResponse":
        return cls(
            id=order.id,
            number=order.number,
            customer_id=order.customer_id,
            status=order.status,
            lines=[OrderLineResponse.from_line(line) for line in order.lines],
            total=order.total.value,
            note=order.note,
            created_at=order.created_at,
            expires_at=order.expires_at,
            closed_at=order.closed_at,
            closing_reason=order.closing_reason,
            decided_by=order.decided_by,
        )


@router.get("")
async def list_orders(
    shop_id: UUID,
    orders: OrdersDep,
    status: OrderStatus | None = None,
    offset: Offset = 0,
    limit: Limit = 50,
) -> Page[OrderResponse]:
    result = await orders.list_orders().execute(
        shop_id=shop_id, status=status, offset=offset, limit=limit
    )
    return Page[OrderResponse](
        items=[OrderResponse.from_order(order) for order in result.items],
        total=result.total,
        offset=result.offset,
        limit=result.limit,
    )


@router.get("/{order_id}")
async def get_order(shop_id: UUID, order_id: UUID, orders: OrdersDep) -> OrderResponse:
    order = await orders.get_order().execute(shop_id=shop_id, order_id=order_id)
    return OrderResponse.from_order(order)


async def _decide(
    shop_id: UUID,
    order_id: UUID,
    accept: bool,
    request: Request,
    account_id: UUID,
    orders: OrdersDep,
) -> OrderResponse:
    order = await orders.decide_order().execute(
        shop_id=shop_id,
        order_id=order_id,
        accept=accept,
        account_id=account_id,
        ip=client_ip(request),
    )
    return OrderResponse.from_order(order)


@router.post("/{order_id}/accept")
async def accept_order(
    shop_id: UUID, order_id: UUID, request: Request, account: CurrentAccount, orders: OrdersDep
) -> OrderResponse:
    return await _decide(shop_id, order_id, True, request, account.id, orders)


@router.post("/{order_id}/refuse")
async def refuse_order(
    shop_id: UUID, order_id: UUID, request: Request, account: CurrentAccount, orders: OrdersDep
) -> OrderResponse:
    return await _decide(shop_id, order_id, False, request, account.id, orders)
