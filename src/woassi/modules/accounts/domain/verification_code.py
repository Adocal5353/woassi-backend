import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5


def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


class CodePurpose(StrEnum):
    PHONE_VERIFICATION = "PHONE_VERIFICATION"
    PASSWORD_RESET = "PASSWORD_RESET"


@dataclass(slots=True)
class VerificationCode:
    id: UUID
    account_id: UUID
    purpose: CodePurpose
    code_hash: str = field(repr=False)
    expires_at: datetime
    created_at: datetime
    attempts: int = 0
    consumed_at: datetime | None = None

    @classmethod
    def issue(
        cls, *, account_id: UUID, purpose: CodePurpose, code_hash: str, now: datetime
    ) -> "VerificationCode":
        return cls(
            id=uuid4(),
            account_id=account_id,
            purpose=purpose,
            code_hash=code_hash,
            expires_at=now + CODE_TTL,
            created_at=now,
        )

    def is_usable(self, now: datetime) -> bool:
        return self.consumed_at is None and self.attempts < MAX_ATTEMPTS and self.expires_at > now

    def record_failure(self) -> None:
        self.attempts += 1

    def consume(self, now: datetime) -> None:
        self.consumed_at = now
