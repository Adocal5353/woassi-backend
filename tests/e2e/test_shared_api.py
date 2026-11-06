from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from tests.fakes import FakeIdempotencyStore, FakeUoW
from woassi.config import Settings
from woassi.main import create_app
from woassi.shared.api.deps import get_authorized_shop, get_shared
from woassi.shared.application.audit import ListAuditEntries
from woassi.shared.application.readiness import CheckReadiness


def allow_shop(shop_id: UUID) -> UUID:
    return shop_id


async def ok() -> None:
    return None


async def failing() -> None:
    raise ConnectionError


class FakeShared:
    def __init__(self) -> None:
        self.uow = FakeUoW()
        self.check = ok

    def list_audit_entries(self) -> ListAuditEntries:
        return ListAuditEntries(self.uow)

    def check_readiness(self) -> CheckReadiness:
        return CheckReadiness({"postgres": ok, "redis": self.check})

    def idempotency_store(self) -> FakeIdempotencyStore:
        return FakeIdempotencyStore()


@pytest.fixture
def shared() -> FakeShared:
    return FakeShared()


@pytest.fixture
def client(settings: Settings, shared: FakeShared) -> TestClient:
    app = create_app(settings)
    app.dependency_overrides[get_shared] = lambda: shared
    app.dependency_overrides[get_authorized_shop] = allow_shop
    return TestClient(app)


def test_health_stays_a_simple_ok(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_ready(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"postgres": "ok", "redis": "ok"}}


def test_not_ready(client: TestClient, shared: FakeShared) -> None:
    shared.check = failing
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "checks": {"postgres": "ok", "redis": "failed"},
    }


async def test_audit_log_returns_a_page(client: TestClient, shared: FakeShared) -> None:
    shop_id = uuid4()
    await shared.uow.audit.record(
        account_id=uuid4(),
        action="order.validated",
        target_type="order",
        target_id="42",
        shop_id=shop_id,
        details={"total": 5000},
        ip="203.0.113.7",
    )

    page = client.get(f"/shops/{shop_id}/audit-log", params={"limit": 10}).json()

    assert (page["total"], page["offset"], page["limit"]) == (1, 0, 10)
    assert page["items"][0]["action"] == "order.validated"
    assert page["items"][0]["details"] == {"total": 5000}


@pytest.mark.parametrize("params", [{"offset": -1}, {"limit": 0}, {"limit": 101}])
def test_audit_log_pagination_limits(client: TestClient, params: dict[str, int]) -> None:
    assert client.get(f"/shops/{uuid4()}/audit-log", params=params).status_code == 422
