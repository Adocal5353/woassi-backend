from woassi.shared.application.ports import RateLimiter
from woassi.shared.domain.errors import RateLimited

LOGIN_LIMIT = 5
LOGIN_WINDOW_S = 15 * 60
CODE_LIMIT = 3
CODE_WINDOW_S = 3600


def login_phone_key(phone: str) -> str:
    return f"login:phone:{phone}"


def login_ip_key(ip: str) -> str:
    return f"login:ip:{ip}"


def code_key(phone: str) -> str:
    return f"code:{phone}"


def password_change_key(account_id: object) -> str:
    return f"password-change:{account_id}"


async def enforce(limiter: RateLimiter, key: str, limit: int, window_s: int) -> None:
    retry_after_s = await limiter.hit(key, limit, window_s)
    if retry_after_s is not None:
        raise RateLimited("Too many attempts. Try again later.", retry_after_s=retry_after_s)
