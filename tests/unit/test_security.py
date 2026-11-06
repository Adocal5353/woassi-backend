from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from woassi.modules.accounts.application.ports import InvalidAccessToken
from woassi.modules.accounts.infrastructure.security import Argon2PasswordHasher, JwtTokenService
from woassi.shared.infrastructure.clock import FrozenClock

SECRET = "test-secret-of-at-least-32-characters"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def service(clock: FrozenClock | None = None, secret: str = SECRET) -> JwtTokenService:
    return JwtTokenService(secret, 900, clock or FrozenClock(NOW))


def claims(**overrides: object) -> dict[str, object]:
    issued_at = int(NOW.timestamp())
    return {
        "sub": str(uuid4()),
        "type": "access",
        "jti": "x",
        "iat": issued_at,
        "exp": issued_at + 900,
        **overrides,
    }


def test_round_trip() -> None:
    account_id = uuid4()
    access = service().issue_access_token(account_id)
    assert access.expires_in == 900
    assert service().verify_access_token(access.token) == account_id


def test_claims() -> None:
    account_id = uuid4()
    decoded = jwt.decode(
        service().issue_access_token(account_id).token,
        options={"verify_signature": False},
    )
    assert decoded["sub"] == str(account_id)
    assert decoded["type"] == "access"
    assert decoded["exp"] - decoded["iat"] == 900
    assert decoded["jti"]


def test_each_token_has_its_own_jti() -> None:
    account_id = uuid4()
    first = service().issue_access_token(account_id).token
    second = service().issue_access_token(account_id).token
    assert first != second


def test_expires_after_its_lifetime() -> None:
    clock = FrozenClock(NOW)
    token = service(clock).issue_access_token(uuid4()).token

    clock.advance(timedelta(seconds=899))
    service(clock).verify_access_token(token)

    clock.advance(timedelta(seconds=1))
    with pytest.raises(InvalidAccessToken):
        service(clock).verify_access_token(token)


@pytest.mark.parametrize(
    "token",
    [
        "",
        "garbage",
        jwt.encode(claims(), "another-secret-of-at-least-32-characters", algorithm="HS256"),
        jwt.encode(claims(type="refresh"), SECRET, algorithm="HS256"),
        jwt.encode(claims(sub="not-a-uuid"), SECRET, algorithm="HS256"),
        jwt.encode({"sub": str(uuid4())}, SECRET, algorithm="HS256"),
    ],
    ids=["empty", "garbage", "wrong-secret", "wrong-type", "bad-sub", "missing-claims"],
)
def test_rejects_invalid_tokens(token: str) -> None:
    with pytest.raises(InvalidAccessToken):
        service().verify_access_token(token)


@pytest.mark.filterwarnings("ignore:The HMAC key")
def test_rejects_another_algorithm() -> None:
    with pytest.raises(InvalidAccessToken):
        service().verify_access_token(jwt.encode(claims(), SECRET, algorithm="HS512"))


def test_rejects_unsigned_tokens() -> None:
    token = jwt.encode(claims(), key="", algorithm="none")
    with pytest.raises(InvalidAccessToken):
        service().verify_access_token(token)


def test_refresh_tokens_are_random_and_stored_as_sha256() -> None:
    tokens = service()
    first, second = tokens.new_refresh_token(), tokens.new_refresh_token()
    assert first != second
    assert len(first) >= 43
    hashed = tokens.hash_refresh_token(first)
    assert len(hashed) == 64
    assert first not in hashed
    assert hashed == tokens.hash_refresh_token(first)


async def test_argon2_round_trip() -> None:
    hasher = Argon2PasswordHasher()
    hashed = await hasher.hash("correct horse")
    assert hashed.startswith("$argon2")
    assert await hasher.verify("correct horse", hashed)
    assert not await hasher.verify("wrong horse", hashed)


async def test_argon2_treats_a_corrupted_hash_as_a_failure() -> None:
    assert not await Argon2PasswordHasher().verify("x", "not-a-hash")


async def test_dummy_verify_accepts_nothing_and_raises_nothing() -> None:
    assert await Argon2PasswordHasher().dummy_verify("anything") is None
