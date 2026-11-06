from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class MetaEvent:
    """Incoming WhatsApp message; `phone_number_id` identifies the target shop.

    `sender` and `payload` are personal data: repr=False keeps them out of logs, including
    arq's, which logs the repr of every job's arguments.
    """

    phone_number_id: str
    message_id: str
    sender: str = field(repr=False)
    type: str
    payload: Mapping[str, Any] = field(repr=False)
