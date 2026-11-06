import hmac
import json

from woassi.modules.messaging.application.extraction import extract_events
from woassi.modules.messaging.application.ports import EventQueue
from woassi.modules.messaging.application.signature import is_valid_signature
from woassi.modules.messaging.domain.errors import InvalidSignature, VerificationRefused
from woassi.shared.domain.errors import InvalidData


class VerifyMetaSubscription:
    def __init__(self, verify_token: str) -> None:
        self._verify_token = verify_token

    def execute(self, *, mode: str | None, token: str | None, challenge: str | None) -> str:
        token_is_valid = hmac.compare_digest((token or "").encode(), self._verify_token.encode())
        if mode != "subscribe" or not token_is_valid or challenge is None:
            raise VerificationRefused("Webhook verification refused.")
        return challenge


class ReceiveMetaWebhook:
    def __init__(self, app_secret: str, queue: EventQueue) -> None:
        self._app_secret = app_secret
        self._queue = queue

    async def execute(self, *, body: bytes, signature: str | None) -> int:
        """Enqueue the webhook events and return how many there were."""
        if not is_valid_signature(body, signature, self._app_secret):
            raise InvalidSignature("Invalid webhook signature.")
        try:
            payload = json.loads(body)
        except ValueError as error:
            raise InvalidData("Unreadable webhook body.") from error
        if not isinstance(payload, dict):
            raise InvalidData("Unexpected webhook body.")

        events = extract_events(payload)
        for event in events:
            await self._queue.enqueue(event)
        return len(events)
