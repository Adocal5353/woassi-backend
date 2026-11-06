import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from tests.fakes import FakeEventQueue
from woassi.config import Settings
from woassi.main import create_app
from woassi.modules.messaging.api.deps import get_messaging
from woassi.modules.messaging.application.use_cases.webhook import (
    ReceiveMetaWebhook,
    VerifyMetaSubscription,
)

SECRET = "app-secret"
TOKEN = "verify-token"
BODY = json.dumps(
    {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "111"},
                            "messages": [
                                {"from": "1", "id": "a", "type": "text", "text": {"body": "x"}},
                                {"from": "1", "id": "b", "type": "text", "text": {"body": "y"}},
                            ],
                        }
                    }
                ]
            }
        ]
    }
).encode()


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


class FakeMessaging:
    def __init__(self, queue: FakeEventQueue) -> None:
        self.queue = queue

    def verify_meta_subscription(self) -> VerifyMetaSubscription:
        return VerifyMetaSubscription(TOKEN)

    def receive_meta_webhook(self) -> ReceiveMetaWebhook:
        return ReceiveMetaWebhook(SECRET, self.queue)


@pytest.fixture
def queue() -> FakeEventQueue:
    return FakeEventQueue()


@pytest.fixture
def client(settings: Settings, queue: FakeEventQueue) -> TestClient:
    app = create_app(settings)
    app.dependency_overrides[get_messaging] = lambda: FakeMessaging(queue)
    return TestClient(app)  # no `with`: the lifespan does not start


def test_verification_succeeds(client: TestClient) -> None:
    response = client.get(
        "/webhooks/meta",
        params={"hub.mode": "subscribe", "hub.verify_token": TOKEN, "hub.challenge": "1158201444"},
    )
    assert response.status_code == 200
    assert response.text == "1158201444"
    assert response.headers["content-type"].startswith("text/plain")


@pytest.mark.parametrize(
    "params",
    [
        {"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "1"},
        {"hub.mode": "unsubscribe", "hub.verify_token": TOKEN, "hub.challenge": "1"},
        {"hub.mode": "subscribe", "hub.verify_token": TOKEN},
        {},
    ],
)
def test_verification_refused(client: TestClient, params: dict[str, str]) -> None:
    response = client.get("/webhooks/meta", params=params)
    assert response.status_code == 403
    assert response.json()["code"] == "messaging.verification_refused"


def test_valid_signature_enqueues(client: TestClient, queue: FakeEventQueue) -> None:
    response = client.post(
        "/webhooks/meta", content=BODY, headers={"X-Hub-Signature-256": sign(BODY)}
    )
    assert response.status_code == 200
    assert [e.message_id for e in queue.events] == ["a", "b"]


def test_invalid_signature(client: TestClient, queue: FakeEventQueue) -> None:
    response = client.post(
        "/webhooks/meta", content=BODY, headers={"X-Hub-Signature-256": "sha256=" + "0" * 64}
    )
    assert response.status_code == 401
    assert response.json()["code"] == "messaging.invalid_signature"
    assert queue.events == []


def test_missing_signature(client: TestClient, queue: FakeEventQueue) -> None:
    assert client.post("/webhooks/meta", content=BODY).status_code == 401
    assert queue.events == []


def test_signed_but_unreadable_body(client: TestClient) -> None:
    body = b"not json"
    response = client.post(
        "/webhooks/meta", content=body, headers={"X-Hub-Signature-256": sign(body)}
    )
    assert response.status_code == 422
