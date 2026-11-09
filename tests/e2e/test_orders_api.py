from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, Header
from fastapi.testclient import TestClient

from tests.orders_fakes import FakeOrdersUoW, OrdersStack
from woassi.config import Settings
from woassi.main import create_app
from woassi.modules.orders.api.deps import get_orders
from woassi.modules.orders.application.use_cases.orders import DecideOrder, GetOrder, ListOrders
from woassi.modules.orders.domain.order import Order
from woassi.shared.api.deps import get_authorized_shop, get_current_account
from woassi.shared.application.ports import AuthenticatedAccount

ACCOUNT = uuid4()


class Facade:
    def __init__(self, stack: OrdersStack) -> None:
        self.stack = stack

    def list_orders(self) -> ListOrders:
        return ListOrders(FakeOrdersUoW(self.stack))

    def get_order(self) -> GetOrder:
        return GetOrder(FakeOrdersUoW(self.stack))

    def decide_order(self) -> DecideOrder:
        return self.stack._flow(DecideOrder)


@pytest.fixture
def stack() -> OrdersStack:
    stack = OrdersStack()
    stack.catalog.add("SKU-PAGNE", "Pagne wax", 5000, stock=10)
    return stack


@pytest.fixture
def client(settings: Settings, stack: OrdersStack) -> TestClient:
    app: FastAPI = create_app(settings)
    app.dependency_overrides[get_orders] = lambda: Facade(stack)
    app.dependency_overrides[get_current_account] = lambda: AuthenticatedAccount(id=ACCOUNT)

    def only_this_shop(shop_id: UUID, x_test: str = Header(default="")) -> UUID:
        if shop_id != stack.shop_id:
            from woassi.shared.domain.errors import ShopNotFound

            raise ShopNotFound("not yours")
        return shop_id

    app.dependency_overrides[get_authorized_shop] = only_this_shop
    return TestClient(app)


async def order(stack: OrdersStack, message_id: str = "wamid.1") -> Order:
    return await stack.receive(("SKU-PAGNE", 2), message_id=message_id)


async def test_list_and_get(client: TestClient, stack: OrdersStack) -> None:
    first, second = await order(stack, "a"), await order(stack, "b")
    base = f"/shops/{stack.shop_id}/orders"

    page = client.get(base).json()
    assert page["total"] == 2
    assert {item["number"] for item in page["items"]} == {first.number, second.number}

    detail = client.get(f"{base}/{first.id}").json()
    assert detail["status"] == "AWAITING_MERCHANT"
    assert detail["total"] == 10000
    assert detail["lines"] == [
        {
            "retailer_id": "SKU-PAGNE",
            "product_id": detail["lines"][0]["product_id"],
            "name": "Pagne wax",
            "unit_price": 5000,
            "requested": 2,
            "quantity": 2,
            "subtotal": 10000,
        }
    ]


async def test_filter_by_status(client: TestClient, stack: OrdersStack) -> None:
    pending, accepted = await order(stack, "a"), await order(stack, "b")
    client.post(f"/shops/{stack.shop_id}/orders/{accepted.id}/accept")
    page = client.get(
        f"/shops/{stack.shop_id}/orders", params={"status": "AWAITING_MERCHANT"}
    ).json()
    assert [item["id"] for item in page["items"]] == [str(pending.id)]


async def test_accept_from_the_dashboard(client: TestClient, stack: OrdersStack) -> None:
    pending = await order(stack)
    response = client.post(f"/shops/{stack.shop_id}/orders/{pending.id}/accept")
    assert response.status_code == 200
    assert response.json()["status"] == "CONFIRMED"
    assert response.json()["decided_by"] == "MERCHANT"
    [entry] = stack.audit_log.entries
    assert (entry.action, entry.account_id) == ("order.validated", ACCOUNT)


async def test_refuse_from_the_dashboard(client: TestClient, stack: OrdersStack) -> None:
    pending = await order(stack)
    response = client.post(f"/shops/{stack.shop_id}/orders/{pending.id}/refuse")
    assert response.json()["closing_reason"] == "MERCHANT_REFUSED"
    assert stack.catalog.stock("SKU-PAGNE") == 10


async def test_deciding_twice_is_a_conflict(client: TestClient, stack: OrdersStack) -> None:
    pending = await order(stack)
    client.post(f"/shops/{stack.shop_id}/orders/{pending.id}/accept")
    response = client.post(f"/shops/{stack.shop_id}/orders/{pending.id}/refuse")
    assert response.status_code == 409
    assert response.json()["code"] == "orders.order_not_open"


async def test_unknown_order(client: TestClient, stack: OrdersStack) -> None:
    response = client.get(f"/shops/{stack.shop_id}/orders/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["code"] == "orders.order_not_found"


async def test_orders_of_another_shop(client: TestClient, stack: OrdersStack) -> None:
    pending = await order(stack)
    other = uuid4()
    assert client.get(f"/shops/{other}/orders").status_code == 404
    assert client.post(f"/shops/{other}/orders/{pending.id}/accept").status_code == 404
