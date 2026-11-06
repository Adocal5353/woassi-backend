from collections.abc import Mapping, Sequence
from typing import Any

from woassi.modules.messaging.domain.event import MetaEvent


def _mappings(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return [element for element in value if isinstance(element, Mapping)]


def _to_event(phone_number_id: str, message: Mapping[str, Any]) -> MetaEvent | None:
    message_id = message.get("id")
    sender = message.get("from")
    message_type = message.get("type")
    if not (message_id and sender and message_type):
        return None
    content = message.get(message_type)
    return MetaEvent(
        phone_number_id=phone_number_id,
        message_id=message_id,
        sender=sender,
        type=message_type,
        payload=content if isinstance(content, Mapping) else {},
    )


def extract_events(payload: Mapping[str, Any]) -> list[MetaEvent]:
    """Extract the messages of a webhook payload: entry → changes → value → messages.

    Lenient: a malformed item is skipped so the rest of the batch is not lost. Other
    notifications (delivery statuses, etc.) have no `messages` and produce nothing.
    """
    events: list[MetaEvent] = []
    for entry in _mappings(payload.get("entry")):
        for change in _mappings(entry.get("changes")):
            value = change.get("value")
            if not isinstance(value, Mapping):
                continue
            metadata = value.get("metadata")
            phone_number_id = (
                metadata.get("phone_number_id") if isinstance(metadata, Mapping) else None
            )
            if not phone_number_id:
                continue
            for message in _mappings(value.get("messages")):
                event = _to_event(phone_number_id, message)
                if event is not None:
                    events.append(event)
    return events
