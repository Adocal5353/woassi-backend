import pytest
from fastapi import Depends, FastAPI, Response
from fastapi.testclient import TestClient
from pydantic import BaseModel

from tests.fakes import FakeIdempotencyStore
from woassi.config import Settings
from woassi.main import create_app
from woassi.shared.api.deps import get_shared
from woassi.shared.api.idempotency import REPLAY_HEADER, idempotent
from woassi.shared.domain.errors import InvalidData


class Body(BaseModel):
    value: int = 0


class Counters:
    calls = 0


class FakeShared:
    def __init__(self, store: FakeIdempotencyStore) -> None:
        self.store = store

    def idempotency_store(self) -> FakeIdempotencyStore:
        return self.store


@pytest.fixture
def store() -> FakeIdempotencyStore:
    return FakeIdempotencyStore()


@pytest.fixture
def counters() -> Counters:
    return Counters()


@pytest.fixture
def app(settings: Settings, store: FakeIdempotencyStore, counters: Counters) -> FastAPI:
    app = create_app(settings)
    app.dependency_overrides[get_shared] = lambda: FakeShared(store)
    guarded = [Depends(idempotent)]

    @app.post("/things", status_code=201, dependencies=guarded)
    async def create_thing(body: Body) -> dict[str, int]:
        counters.calls += 1
        return {"call": counters.calls, "value": body.value}

    @app.post("/refused", dependencies=guarded)
    async def refused() -> None:
        counters.calls += 1
        raise InvalidData("Refused.")

    @app.post("/crash", dependencies=guarded)
    async def crash() -> None:
        counters.calls += 1
        raise RuntimeError("boom")

    @app.post("/unavailable", dependencies=guarded)
    async def unavailable() -> Response:
        counters.calls += 1
        return Response(status_code=503)

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def headers(key: str = "key-1") -> dict[str, str]:
    return {"Idempotency-Key": key}


def test_without_the_header_every_request_runs(client: TestClient, counters: Counters) -> None:
    client.post("/things", json={})
    client.post("/things", json={})
    assert counters.calls == 2


def test_same_key_replays_the_first_response(client: TestClient, counters: Counters) -> None:
    first = client.post("/things", json={"value": 1}, headers=headers())
    second = client.post("/things", json={"value": 1}, headers=headers())

    assert counters.calls == 1
    assert REPLAY_HEADER not in first.headers
    assert second.headers[REPLAY_HEADER] == "true"
    assert (second.status_code, second.content) == (201, first.content)
    assert second.headers["content-type"] == "application/json"


def test_another_key_runs_again(client: TestClient, counters: Counters) -> None:
    client.post("/things", json={}, headers=headers("a"))
    client.post("/things", json={}, headers=headers("b"))
    assert counters.calls == 2


def test_same_key_on_another_route_is_independent(client: TestClient, counters: Counters) -> None:
    client.post("/things", json={}, headers=headers())
    client.post("/refused", headers=headers())
    assert counters.calls == 2


def test_same_key_with_another_body_is_refused(client: TestClient, counters: Counters) -> None:
    client.post("/things", json={"value": 1}, headers=headers())
    response = client.post("/things", json={"value": 2}, headers=headers())

    assert response.status_code == 422
    assert response.json()["code"] == "idempotency.key_reused"
    assert counters.calls == 1


async def test_a_request_still_running_is_a_conflict(
    client: TestClient, store: FakeIdempotencyStore, counters: Counters
) -> None:
    client.post("/things", json={}, headers=headers())
    key, record = next(iter(store.records.items()))
    await store.release(key)
    await store.begin(key, record.fingerprint)

    response = client.post("/things", json={}, headers=headers())

    assert response.status_code == 409
    assert response.json()["code"] == "idempotency.in_progress"
    assert counters.calls == 1


def test_a_business_error_is_replayed(client: TestClient, counters: Counters) -> None:
    first = client.post("/refused", headers=headers())
    second = client.post("/refused", headers=headers())

    assert first.status_code == second.status_code == 422
    assert second.headers[REPLAY_HEADER] == "true"
    assert counters.calls == 1


@pytest.mark.parametrize("path", ["/crash", "/unavailable"])
def test_a_server_error_can_be_retried(
    client: TestClient, counters: Counters, store: FakeIdempotencyStore, path: str
) -> None:
    assert client.post(path, headers=headers()).status_code >= 500
    assert store.records == {}

    client.post(path, headers=headers())
    assert counters.calls == 2


def test_too_long_a_key_is_refused(client: TestClient) -> None:
    response = client.post("/things", json={}, headers=headers("x" * 256))
    assert response.status_code == 422
