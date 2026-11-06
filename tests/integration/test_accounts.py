import asyncio
from collections.abc import Awaitable

import pytest
from arq.connections import ArqRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.fakes import FakeCodeSender
from woassi.modules.accounts.application.dto import TokenPair
from woassi.modules.accounts.application.use_cases.registration import Register, VerifyPhone
from woassi.modules.accounts.application.use_cases.session import Login, RefreshTokens
from woassi.modules.accounts.domain.errors import (
    InvalidCode,
    InvalidRefreshToken,
    PhoneAlreadyUsed,
)
from woassi.modules.accounts.domain.events import AccountCreated, AccountLoggedIn
from woassi.modules.accounts.domain.verification_code import MAX_ATTEMPTS
from woassi.modules.accounts.infrastructure.models import (
    AccountModel,
    RefreshTokenModel,
    VerificationCodeModel,
)
from woassi.modules.accounts.infrastructure.security import Argon2PasswordHasher, JwtTokenService
from woassi.modules.accounts.infrastructure.uow import SqlAlchemyAccountsUoW
from woassi.shared.domain.errors import RateLimited
from woassi.shared.domain.events import DomainEvent
from woassi.shared.infrastructure.clock import SystemClock
from woassi.shared.infrastructure.events.bus import InProcessEventBus
from woassi.shared.infrastructure.phone import PhonenumbersNormalizer
from woassi.shared.infrastructure.rate_limiter import RedisRateLimiter

pytestmark = pytest.mark.integration

PHONE = "90 12 34 56"
PASSWORD = "correct-horse"
HASHER = Argon2PasswordHasher()


class Real:
    """Argon2, JWT, PostgreSQL and Redis: everything but the code sender."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], pool: ArqRedis) -> None:
        self.sessions = sessions
        self.clock = SystemClock()
        self.bus = InProcessEventBus()
        self.sender = FakeCodeSender()
        self.limiter = RedisRateLimiter(pool)
        self.phones = PhonenumbersNormalizer()
        self.tokens = JwtTokenService("test-secret-of-at-least-32-characters", 900, self.clock)

    def uow(self) -> SqlAlchemyAccountsUoW:
        return SqlAlchemyAccountsUoW(self.sessions, self.bus, self.clock)

    def register(self) -> Register:
        return Register(self.uow(), HASHER, self.sender, self.limiter, self.phones, self.clock)

    def verify_phone(self) -> VerifyPhone:
        return VerifyPhone(self.uow(), HASHER, self.phones, self.clock)

    def login(self) -> Login:
        return Login(
            self.uow(),
            HASHER,
            self.tokens,
            self.limiter,
            self.phones,
            self.clock,
            refresh_ttl_s=3600,
        )

    def refresh(self) -> RefreshTokens:
        return RefreshTokens(self.uow(), self.tokens, self.clock, refresh_ttl_s=3600)


@pytest.fixture
def real(sessions: async_sessionmaker[AsyncSession], pool: ArqRedis) -> Real:
    return Real(sessions, pool)


async def signed_in(real: Real) -> TokenPair:
    await real.register().execute(full_name="Ama", phone=PHONE, password=PASSWORD)
    return await real.login().execute(phone=PHONE, password=PASSWORD, ip="203.0.113.7")


async def outcomes(*calls: Awaitable[object]) -> list[object]:
    return await asyncio.gather(*calls, return_exceptions=True)


async def test_whole_journey_on_real_adapters(real: Real) -> None:
    events: list[DomainEvent] = []

    async def collect(event: DomainEvent) -> None:
        events.append(event)

    real.bus.subscribe(AccountCreated, collect, name="created")
    real.bus.subscribe(AccountLoggedIn, collect, name="logged-in")

    await real.register().execute(full_name="Ama", phone=PHONE, password=PASSWORD)
    await real.verify_phone().execute(phone=PHONE, code=real.sender.last_code)

    first = await real.login().execute(phone=PHONE, password=PASSWORD, ip="203.0.113.7")
    second = await real.refresh().execute(first.refresh_token)

    with pytest.raises(InvalidRefreshToken):
        await real.refresh().execute(first.refresh_token)
    with pytest.raises(InvalidRefreshToken):
        await real.refresh().execute(second.refresh_token)
    assert [type(event) for event in events] == [AccountCreated, AccountLoggedIn]


async def test_no_secret_is_stored_in_clear(real: Real) -> None:
    pair = await signed_in(real)
    async with real.sessions() as session:
        account = await session.scalar(select(AccountModel))
        token = await session.scalar(select(RefreshTokenModel))
        code = await session.scalar(select(VerificationCodeModel))

    assert account is not None and token is not None and code is not None
    assert account.password_hash.startswith("$argon2")
    assert token.token_hash == real.tokens.hash_refresh_token(pair.refresh_token)
    assert real.sender.last_code not in code.code_hash


async def test_concurrent_registrations_of_one_phone(real: Real) -> None:
    results = await outcomes(
        *(
            real.register().execute(full_name="Ama", phone=PHONE, password=PASSWORD)
            for _ in range(3)
        )
    )
    errors = [result for result in results if isinstance(result, Exception)]
    assert len(errors) == 2
    assert all(isinstance(error, PhoneAlreadyUsed) for error in errors)


async def test_concurrent_refreshes_cannot_both_succeed(real: Real) -> None:
    pair = await signed_in(real)

    results = await outcomes(*(real.refresh().execute(pair.refresh_token) for _ in range(5)))

    winners = [result for result in results if isinstance(result, TokenPair)]
    assert len(winners) <= 1
    assert all(
        isinstance(result, InvalidRefreshToken)
        for result in results
        if not isinstance(result, TokenPair)
    )
    # A replay happened, so the whole family is dead, the winner's new token included.
    for winner in winners:
        with pytest.raises(InvalidRefreshToken):
            await real.refresh().execute(winner.refresh_token)


async def test_failed_attempts_survive_their_transaction(real: Real) -> None:
    await real.register().execute(full_name="Ama", phone=PHONE, password=PASSWORD)
    wrong = "000000" if real.sender.last_code != "000000" else "111111"

    for _ in range(MAX_ATTEMPTS):
        with pytest.raises(InvalidCode):
            await real.verify_phone().execute(phone=PHONE, code=wrong)

    with pytest.raises(InvalidCode):
        await real.verify_phone().execute(phone=PHONE, code=real.sender.last_code)


async def test_concurrent_attempts_are_all_counted(real: Real) -> None:
    await real.register().execute(full_name="Ama", phone=PHONE, password=PASSWORD)
    wrong = "000000" if real.sender.last_code != "000000" else "111111"

    await outcomes(
        *(real.verify_phone().execute(phone=PHONE, code=wrong) for _ in range(MAX_ATTEMPTS * 2))
    )

    async with real.sessions() as session:
        code = await session.scalar(select(VerificationCodeModel))
    assert code is not None
    assert code.attempts == MAX_ATTEMPTS


async def test_concurrent_login_guesses_cannot_beat_the_limit(real: Real) -> None:
    await real.register().execute(full_name="Ama", phone=PHONE, password=PASSWORD)

    results = await outcomes(
        *(
            real.login().execute(phone=PHONE, password="wrong-password", ip=f"203.0.113.{n}")
            for n in range(12)
        )
    )

    assert len([result for result in results if isinstance(result, RateLimited)]) == 7


async def test_limiter_allows_up_to_the_limit(pool: ArqRedis) -> None:
    limiter = RedisRateLimiter(pool)
    results = [await limiter.hit("k", 3, 60) for _ in range(4)]

    assert results[:3] == [None, None, None]
    assert results[3] is not None
    assert 0 < results[3] <= 60


async def test_limiter_is_atomic(pool: ArqRedis) -> None:
    limiter = RedisRateLimiter(pool)
    results = await asyncio.gather(*(limiter.hit("k", 5, 60) for _ in range(20)))
    assert len([result for result in results if result is None]) == 5


async def test_limiter_window_expires(pool: ArqRedis) -> None:
    limiter = RedisRateLimiter(pool)
    await limiter.hit("k", 1, 60)
    assert await limiter.hit("k", 1, 60) is not None

    await pool.expire("rate:k", 0)

    assert await limiter.hit("k", 1, 60) is None


async def test_every_counter_has_an_expiry(pool: ArqRedis) -> None:
    await RedisRateLimiter(pool).hit("k", 1, 60)
    assert 0 < await pool.ttl("rate:k") <= 60


async def test_forgive_gives_an_attempt_back(pool: ArqRedis) -> None:
    limiter = RedisRateLimiter(pool)
    await limiter.hit("k", 1, 60)
    await limiter.forgive("k")
    assert await limiter.hit("k", 1, 60) is None


async def test_forgiving_an_expired_key_leaves_nothing_behind(pool: ArqRedis) -> None:
    await RedisRateLimiter(pool).forgive("k")
    assert await pool.exists("rate:k") == 0
