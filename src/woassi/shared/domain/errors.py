class DomainError(Exception):
    """Business error. `code` is stable: API clients can rely on it."""

    code = "domain_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class NotFound(DomainError):
    code = "not_found"


class InvalidData(DomainError):
    code = "invalid_data"


class Conflict(DomainError):
    code = "conflict"


class Unauthorized(DomainError):
    code = "auth.unauthorized"


class Forbidden(DomainError):
    code = "auth.forbidden"


class RateLimited(DomainError):
    code = "rate_limited"

    def __init__(self, message: str, *, retry_after_s: int) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class ObjectNotFound(NotFound):
    """Object missing from storage."""

    code = "storage.object_not_found"


class IdempotencyInProgress(Conflict):
    code = "idempotency.in_progress"


class IdempotencyKeyReused(InvalidData):
    code = "idempotency.key_reused"


class ShopNotFound(NotFound):
    code = "shops.not_found"
