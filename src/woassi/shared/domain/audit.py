from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AuditEntry:
    id: UUID
    account_id: UUID
    shop_id: UUID | None
    action: str
    target_type: str
    target_id: str
    details: Mapping[str, Any]
    ip: str | None
    created_at: datetime
