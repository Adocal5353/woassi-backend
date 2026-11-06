from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.fakes import (
    AccountsState,
    FakeAccountsUoW,
    FakeCodeSender,
    FakePasswordHasher,
    FakeRateLimiter,
)
from woassi.config import Settings
from woassi.integration.accounts import AccountsAuthenticator
from woassi.main import create_app
from woassi.modules.accounts.api.deps import get_accounts
from woassi.modules.accounts.application.use_cases.password import (
    ChangePassword,
    RequestPasswordReset,
    ResetPassword,
)
from woassi.modules.accounts.application.use_cases.profile import GetMyAccount, UpdateMyAccount
from woassi.modules.accounts.application.use_cases.registration import Register, VerifyPhone
from woassi.modules.accounts.application.use_cases.session import (
    AuthenticateAccount,
    Login,
    Logout,
    LogoutEverywhere,
    RefreshTokens,
)
from woassi.modules.accounts.domain.account import AccountStatus
from woassi.modules.accounts.domain.errors import InvalidCredentials
from woassi.modules.accounts.domain.events import AccountCreated, AccountLoggedIn
from woassi.modules.accounts.infrastructure.security import JwtTokenService
from woassi.modules.messaging.api.deps import get_messaging
from woassi.modules.messaging.application.use_cases.webhook import VerifyMetaSubscription
from woassi.shared.api.deps import get_shared
from woassi.shared.domain.errors import RateLimited
from woassi.shared.domain.events import DomainEvent
from woassi.shared.domain.values import PhoneNumber
from woassi.shared.infrastructure.clock import FrozenClock
from woassi.shared.infrastructure.phone import PhonenumbersNormalizer

PHONE = "90 12 34 56"
E164 = "+22890123456"
PASSWORD = "correct-horse"
THIRTY_DAYS = 30 * 24 * 3600


class DenyAllShopOwnership:
    async def owns(self, account_id: UUID, shop_id: UUID) -> bool:
        return False


class Stack:
    """The real use cases and routers, on in-memory adapters."""

    def __init__(self) -> None:
        self.database = AccountsState()
        self.events: list[DomainEvent] = []
        self.hasher = FakePasswordHasher()
        self.sender = FakeCodeSender()
        self.limiter = FakeRateLimiter()
        self.phones = PhonenumbersNormalizer()
        self.clock = FrozenClock(datetime(2026, 1, 1, tzinfo=UTC))
        self.tokens = JwtTokenService("test-secret-of-at-least-32-characters", 900, self.clock)

    def uow(self) -> FakeAccountsUoW:
        return FakeAccountsUoW(self.database, self.events)

    def register(self) -> Register:
        return Register(self.uow(), self.hasher, self.sender, self.limiter, self.phones, self.clock)

    def verify_phone(self) -> VerifyPhone:
        return VerifyPhone(self.uow(), self.hasher, self.phones, self.clock)

    def login(self) -> Login:
        return Login(
            self.uow(),
            self.hasher,
            self.tokens,
            self.limiter,
            self.phones,
            self.clock,
            refresh_ttl_s=THIRTY_DAYS,
        )

    def refresh_tokens(self) -> RefreshTokens:
        return RefreshTokens(self.uow(), self.tokens, self.clock, refresh_ttl_s=THIRTY_DAYS)

    def logout(self) -> Logout:
        return Logout(self.uow(), self.tokens, self.clock)

    def logout_everywhere(self) -> LogoutEverywhere:
        return LogoutEverywhere(self.uow(), self.clock)

    def request_password_reset(self) -> RequestPasswordReset:
        return RequestPasswordReset(
            self.uow(), self.hasher, self.sender, self.limiter, self.phones, self.clock
        )

    def reset_password(self) -> ResetPassword:
        return ResetPassword(self.uow(), self.hasher, self.phones, self.clock)

    def get_my_account(self) -> GetMyAccount:
        return GetMyAccount(self.uow())

    def update_my_account(self) -> UpdateMyAccount:
        return UpdateMyAccount(self.uow())

    def change_password(self) -> ChangePassword:
        return ChangePassword(self.uow(), self.hasher, self.limiter, self.clock)

    def account_authenticator(self) -> AccountsAuthenticator:
        return AccountsAuthenticator(AuthenticateAccount(self.uow(), self.tokens))

    def shop_ownership(self) -> DenyAllShopOwnership:
        return DenyAllShopOwnership()

    def suspend(self) -> None:
        for account in self.database.accounts.values():
            account.status = AccountStatus.SUSPENDED


@pytest.fixture
def stack() -> Stack:
    return Stack()


@pytest.fixture
def client(settings: Settings, stack: Stack) -> TestClient:
    app = create_app(settings)
    app.dependency_overrides[get_accounts] = lambda: stack
    app.dependency_overrides[get_shared] = lambda: stack
    # https: otherwise the client would not send back a Secure cookie
    return TestClient(app, base_url="https://testserver")


def register(client: TestClient, phone: str = PHONE) -> None:
    response = client.post(
        "/auth/register", json={"full_name": "Ama", "phone": phone, "password": PASSWORD}
    )
    assert response.status_code == 201


def login(client: TestClient, password: str = PASSWORD, phone: str = PHONE) -> dict[str, str]:
    response = client.post("/auth/login", json={"phone": phone, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def bearer(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def refresh(client: TestClient, token: str) -> int:
    client.cookies.clear()
    return client.post("/auth/refresh", json={"refresh_token": token}).status_code


@pytest.fixture
def tokens(client: TestClient) -> dict[str, str]:
    register(client)
    return login(client)


# The whole journey


def test_register_verify_login_refresh_then_reuse_revokes_the_family(
    client: TestClient, stack: Stack
) -> None:
    created = client.post(
        "/auth/register",
        json={"full_name": "Ama", "phone": PHONE, "password": PASSWORD, "email": "ama@woassi.tg"},
    )
    assert created.status_code == 201
    assert created.json()["phone"] == E164
    assert created.json()["phone_verified"] is False
    assert "password" not in created.text

    verified = client.post("/auth/verify", json={"phone": PHONE, "code": stack.sender.last_code})
    assert verified.status_code == 204

    first = login(client)
    me = client.get("/me", headers=bearer(first)).json()
    assert me["phone_verified"] is True
    assert me["email"] == "ama@woassi.tg"

    client.cookies.clear()
    rotated = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert rotated.status_code == 200
    second = rotated.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert client.get("/me", headers=bearer(second)).status_code == 200

    # The first token is replayed: someone holds a stolen copy.
    assert refresh(client, first["refresh_token"]) == 401
    # The legitimate latest token dies with it.
    assert refresh(client, second["refresh_token"]) == 401
    assert [type(event) for event in stack.events] == [AccountCreated, AccountLoggedIn]


# Registration


def test_phone_is_unique_whatever_its_format(client: TestClient) -> None:
    register(client)
    response = client.post(
        "/auth/register",
        json={"full_name": "Kofi", "phone": "+228 90 12 34 56", "password": PASSWORD},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "accounts.phone_already_used"


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [("password", "short", "accounts.weak_password"), ("phone", "123", "phone.invalid")],
)
def test_register_validation(
    client: TestClient, stack: Stack, field: str, value: str, code: str
) -> None:
    body = {"full_name": "Ama", "phone": PHONE, "password": PASSWORD, field: value}
    response = client.post("/auth/register", json=body)
    assert response.status_code == 422
    assert response.json()["code"] == code
    assert stack.sender.sent == []


def test_a_code_is_only_sent_once_the_account_is_saved(client: TestClient, stack: Stack) -> None:
    register(client)
    client.post("/auth/register", json={"full_name": "A", "phone": PHONE, "password": PASSWORD})
    assert len(stack.sender.sent) == 1


# Phone verification


def wrong_code(stack: Stack) -> str:
    return "000000" if stack.sender.last_code != "000000" else "111111"


def test_wrong_and_unknown_are_indistinguishable(client: TestClient, stack: Stack) -> None:
    register(client)
    wrong = client.post("/auth/verify", json={"phone": PHONE, "code": wrong_code(stack)})
    unknown = client.post("/auth/verify", json={"phone": "90 99 99 99", "code": "123456"})
    assert wrong.status_code == unknown.status_code == 422
    assert wrong.json() == unknown.json()


def test_code_expires_after_ten_minutes(client: TestClient, stack: Stack) -> None:
    register(client)
    stack.clock.advance(timedelta(minutes=10))
    response = client.post("/auth/verify", json={"phone": PHONE, "code": stack.sender.last_code})
    assert response.status_code == 422


def test_five_wrong_attempts_lock_the_code(client: TestClient, stack: Stack) -> None:
    register(client)
    for _ in range(5):
        client.post("/auth/verify", json={"phone": PHONE, "code": wrong_code(stack)})

    response = client.post("/auth/verify", json={"phone": PHONE, "code": stack.sender.last_code})

    assert response.status_code == 422
    assert client.get("/me").status_code == 401


def test_four_wrong_attempts_do_not(client: TestClient, stack: Stack) -> None:
    register(client)
    for _ in range(4):
        client.post("/auth/verify", json={"phone": PHONE, "code": wrong_code(stack)})
    response = client.post("/auth/verify", json={"phone": PHONE, "code": stack.sender.last_code})
    assert response.status_code == 204


def test_a_code_works_only_once(client: TestClient, stack: Stack) -> None:
    register(client)
    body = {"phone": PHONE, "code": stack.sender.last_code}
    assert client.post("/auth/verify", json=body).status_code == 204
    assert client.post("/auth/verify", json=body).status_code == 422


# Login


@pytest.mark.parametrize(
    "credentials",
    [
        {"phone": PHONE, "password": "wrong-password"},
        {"phone": "90 99 99 99", "password": PASSWORD},
        {"phone": "not a phone", "password": PASSWORD},
    ],
    ids=["wrong-password", "unknown-phone", "malformed-phone"],
)
def test_login_failures_are_neutral(client: TestClient, credentials: dict[str, str]) -> None:
    register(client)
    response = client.post("/auth/login", json=credentials)
    assert response.status_code == 401
    assert response.json() == {
        "code": "auth.invalid_credentials",
        "message": "Invalid credentials.",
    }


def test_suspended_account_cannot_log_in(client: TestClient, stack: Stack) -> None:
    register(client)
    stack.suspend()
    response = client.post("/auth/login", json={"phone": PHONE, "password": PASSWORD})
    assert response.status_code == 403
    assert response.json()["code"] == "accounts.suspended"


def test_a_suspended_account_gets_no_access_to_it_either(client: TestClient, stack: Stack) -> None:
    register(client)
    stack.suspend()
    response = client.post("/auth/login", json={"phone": PHONE, "password": "wrong-password"})
    assert response.status_code == 401


def test_refresh_cookie_attributes(client: TestClient) -> None:
    register(client)
    response = client.post("/auth/login", json={"phone": PHONE, "password": PASSWORD})
    cookie = response.headers["set-cookie"].lower()

    assert response.json()["refresh_token"] in response.headers["set-cookie"]
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie
    assert "path=/auth" in cookie
    assert f"max-age={THIRTY_DAYS}" in cookie


# Rate limiting


def test_five_failed_logins_block_the_phone(client: TestClient) -> None:
    register(client)
    wrong = {"phone": PHONE, "password": "wrong-password"}
    for _ in range(5):
        assert client.post("/auth/login", json=wrong).status_code == 401

    blocked = client.post("/auth/login", json={"phone": PHONE, "password": PASSWORD})

    assert blocked.status_code == 429
    assert blocked.json()["code"] == "rate_limited"
    assert int(blocked.headers["retry-after"]) > 0


async def test_changing_ip_does_not_get_around_the_phone_limit(
    client: TestClient, stack: Stack
) -> None:
    register(client)
    for number in range(5):
        with pytest.raises(InvalidCredentials):
            await stack.login().execute(phone=PHONE, password="x", ip=f"203.0.113.{number}")

    with pytest.raises(RateLimited):
        await stack.login().execute(phone=PHONE, password=PASSWORD, ip="198.51.100.1")


def test_five_failed_logins_block_the_ip_across_phones(client: TestClient) -> None:
    for number in range(5):
        body = {"phone": f"90 12 34 5{number}", "password": "wrong-password"}
        assert client.post("/auth/login", json=body).status_code == 401

    blocked = client.post("/auth/login", json={"phone": "90 99 99 99", "password": "x"})
    assert blocked.status_code == 429


def test_an_unknown_phone_is_limited_like_a_known_one(client: TestClient) -> None:
    body = {"phone": "90 99 99 99", "password": "x"}
    statuses = [client.post("/auth/login", json=body).status_code for _ in range(6)]
    assert statuses == [401] * 5 + [429]


def test_successful_logins_do_not_count(client: TestClient) -> None:
    register(client)
    for _ in range(10):
        login(client)


def test_three_codes_per_hour(client: TestClient, stack: Stack) -> None:
    register(client)  # first code
    body = {"phone": PHONE}
    statuses = [client.post("/auth/password/request", json=body).status_code for _ in range(3)]
    assert statuses == [202, 202, 429]
    assert len(stack.sender.sent) == 3


def test_code_limit_does_not_reveal_whether_the_phone_exists(client: TestClient) -> None:
    body = {"phone": "90 99 99 99"}
    statuses = [client.post("/auth/password/request", json=body).status_code for _ in range(4)]
    assert statuses == [202, 202, 202, 429]


# Refresh


def test_cookie_is_enough_to_refresh(client: TestClient, tokens: dict[str, str]) -> None:
    response = client.post("/auth/refresh")
    assert response.status_code == 200
    assert response.json()["refresh_token"] != tokens["refresh_token"]
    assert response.json()["refresh_token"] in response.headers["set-cookie"]


def test_refresh_needs_a_token(client: TestClient) -> None:
    response = client.post("/auth/refresh")
    assert response.status_code == 401
    assert response.json()["code"] == "auth.invalid_refresh_token"


def test_unknown_refresh_token(client: TestClient) -> None:
    assert refresh(client, "unknown") == 401


def test_refresh_token_expires(client: TestClient, stack: Stack, tokens: dict[str, str]) -> None:
    stack.clock.advance(timedelta(seconds=THIRTY_DAYS))
    assert refresh(client, tokens["refresh_token"]) == 401


def test_reuse_only_revokes_its_own_family(client: TestClient, tokens: dict[str, str]) -> None:
    other_session = login(client)
    assert refresh(client, tokens["refresh_token"]) == 200
    assert refresh(client, tokens["refresh_token"]) == 401
    assert refresh(client, other_session["refresh_token"]) == 200


def test_suspended_account_cannot_refresh(
    client: TestClient, stack: Stack, tokens: dict[str, str]
) -> None:
    stack.suspend()
    assert refresh(client, tokens["refresh_token"]) == 401


# Logout


def test_logout_revokes_the_token_and_clears_the_cookie(
    client: TestClient, tokens: dict[str, str]
) -> None:
    response = client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 204
    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert refresh(client, tokens["refresh_token"]) == 401


def test_logout_uses_the_cookie_too(client: TestClient, tokens: dict[str, str]) -> None:
    assert client.post("/auth/logout").status_code == 204
    assert refresh(client, tokens["refresh_token"]) == 401


def test_logout_leaves_other_sessions_alone(client: TestClient, tokens: dict[str, str]) -> None:
    other_session = login(client)
    client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert refresh(client, other_session["refresh_token"]) == 200


def test_logout_with_nothing_is_harmless(client: TestClient) -> None:
    assert client.post("/auth/logout").status_code == 204
    assert client.post("/auth/logout", json={"refresh_token": "unknown"}).status_code == 204


def test_logout_everywhere(client: TestClient, tokens: dict[str, str]) -> None:
    other_session = login(client)
    assert client.post("/auth/logout-all", headers=bearer(tokens)).status_code == 204
    assert refresh(client, tokens["refresh_token"]) == 401
    assert refresh(client, other_session["refresh_token"]) == 401


def test_logout_everywhere_needs_a_token(client: TestClient) -> None:
    assert client.post("/auth/logout-all").status_code == 401


# Password reset


def test_reset_request_is_neutral(client: TestClient, stack: Stack) -> None:
    register(client)
    known = client.post("/auth/password/request", json={"phone": PHONE})
    unknown = client.post("/auth/password/request", json={"phone": "90 99 99 99"})
    malformed = client.post("/auth/password/request", json={"phone": "nope"})

    assert known.status_code == unknown.status_code == malformed.status_code == 202
    assert known.content == unknown.content == malformed.content
    assert len(stack.sender.sent) == 2


def test_password_reset_journey(client: TestClient, stack: Stack, tokens: dict[str, str]) -> None:
    client.post("/auth/password/request", json={"phone": PHONE})
    response = client.post(
        "/auth/password/reset",
        json={"phone": PHONE, "code": stack.sender.last_code, "new_password": "new-password"},
    )
    assert response.status_code == 204

    # Sessions opened with the old password are over.
    assert refresh(client, tokens["refresh_token"]) == 401
    old = client.post("/auth/login", json={"phone": PHONE, "password": PASSWORD})
    assert old.status_code == 401
    assert client.get("/me", headers=bearer(login(client, "new-password"))).json()["phone_verified"]


def test_verification_code_cannot_reset_a_password(client: TestClient, stack: Stack) -> None:
    register(client)
    response = client.post(
        "/auth/password/reset",
        json={"phone": PHONE, "code": stack.sender.last_code, "new_password": "new-password"},
    )
    assert response.status_code == 422


def test_reset_checks_the_new_password_without_burning_the_code(
    client: TestClient, stack: Stack
) -> None:
    register(client)
    client.post("/auth/password/request", json={"phone": PHONE})
    body = {"phone": PHONE, "code": stack.sender.last_code, "new_password": "short"}
    assert client.post("/auth/password/reset", json=body).status_code == 422

    body["new_password"] = "new-password"
    assert client.post("/auth/password/reset", json=body).status_code == 204


# My account


def test_me_requires_a_token(client: TestClient) -> None:
    response = client.get("/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_me_rejects_an_expired_token(
    client: TestClient, stack: Stack, tokens: dict[str, str]
) -> None:
    stack.clock.advance(timedelta(seconds=900))
    assert client.get("/me", headers=bearer(tokens)).status_code == 401


def test_me_rejects_a_suspended_account(
    client: TestClient, stack: Stack, tokens: dict[str, str]
) -> None:
    stack.suspend()
    assert client.get("/me", headers=bearer(tokens)).status_code == 401


def test_me_rejects_a_token_of_a_deleted_account(
    client: TestClient, stack: Stack, tokens: dict[str, str]
) -> None:
    stack.database.accounts.clear()
    assert client.get("/me", headers=bearer(tokens)).status_code == 401


def test_me_never_returns_the_password_hash(client: TestClient, tokens: dict[str, str]) -> None:
    assert "hash" not in client.get("/me", headers=bearer(tokens)).text


def test_update_me(client: TestClient, tokens: dict[str, str]) -> None:
    headers = bearer(tokens)
    updated = client.patch(
        "/me", headers=headers, json={"full_name": "Ama M.", "email": "ama@woassi.tg"}
    ).json()
    assert (updated["full_name"], updated["email"]) == ("Ama M.", "ama@woassi.tg")

    # What is left out does not change; an explicit null removes the email.
    renamed = client.patch("/me", headers=headers, json={"full_name": "Ama"}).json()
    assert renamed["email"] == "ama@woassi.tg"
    assert client.patch("/me", headers=headers, json={"email": None}).json()["email"] is None


def test_the_phone_cannot_be_changed_through_update(
    client: TestClient, tokens: dict[str, str]
) -> None:
    client.patch("/me", headers=bearer(tokens), json={"phone": "+22891111111"})
    assert client.get("/me", headers=bearer(tokens)).json()["phone"] == E164


@pytest.mark.parametrize("body", [{"email": "not-an-email"}, {"full_name": ""}])
def test_update_me_validation(
    client: TestClient, tokens: dict[str, str], body: dict[str, str]
) -> None:
    assert client.patch("/me", headers=bearer(tokens), json=body).status_code == 422


def test_change_password(client: TestClient, tokens: dict[str, str]) -> None:
    response = client.post(
        "/me/password",
        headers=bearer(tokens),
        json={"current_password": PASSWORD, "new_password": "new-password"},
    )
    assert response.status_code == 204
    assert refresh(client, tokens["refresh_token"]) == 401
    login(client, "new-password")


def test_change_password_needs_the_current_one(client: TestClient, tokens: dict[str, str]) -> None:
    response = client.post(
        "/me/password",
        headers=bearer(tokens),
        json={"current_password": "wrong-password", "new_password": "new-password"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "accounts.wrong_password"
    assert refresh(client, tokens["refresh_token"]) == 200


def test_guessing_the_current_password_is_limited(
    client: TestClient, tokens: dict[str, str]
) -> None:
    body = {"current_password": "wrong-password", "new_password": "new-password"}
    statuses = [
        client.post("/me/password", headers=bearer(tokens), json=body).status_code for _ in range(6)
    ]
    assert statuses == [422] * 5 + [429]


# Access control


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/shops/{shop}/products"),
        ("post", "/shops/{shop}/products"),
        ("get", "/shops/{shop}/products/{other}"),
        ("post", "/shops/{shop}/products/{other}/photos/upload-url"),
        ("post", "/shops/{shop}/products/{other}/photos/{other}/confirm"),
        ("get", "/shops/{shop}/audit-log"),
    ],
)
def test_shop_routes_require_a_token(client: TestClient, method: str, path: str) -> None:
    url = path.format(shop=uuid4(), other=uuid4())
    response = client.request(method, url, json={})
    assert response.status_code == 401
    assert response.json()["code"] == "auth.unauthorized"


def test_an_invalid_token_is_refused(client: TestClient) -> None:
    response = client.get(
        f"/shops/{uuid4()}/products", headers={"Authorization": "Bearer not-a-token"}
    )
    assert response.status_code == 401


def test_a_shop_of_someone_else_looks_like_it_does_not_exist(
    client: TestClient, tokens: dict[str, str]
) -> None:
    shop_id: UUID = uuid4()
    for path in (f"/shops/{shop_id}/products", f"/shops/{shop_id}/audit-log"):
        response = client.get(path, headers=bearer(tokens))
        assert response.status_code == 404
        assert response.json()["code"] == "shops.not_found"


def test_webhooks_and_health_stay_public(client: TestClient) -> None:
    class Messaging:
        def verify_meta_subscription(self) -> VerifyMetaSubscription:
            return VerifyMetaSubscription("verify-token")

    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_messaging] = Messaging
    params = {"hub.mode": "subscribe", "hub.verify_token": "verify-token", "hub.challenge": "42"}

    assert client.get("/health").status_code == 200
    assert client.get("/webhooks/meta", params=params).text == "42"


def test_login_hashes_the_stored_refresh_token(
    client: TestClient, stack: Stack, tokens: dict[str, str]
) -> None:
    stored = next(iter(stack.database.tokens.values()))
    assert stored.token_hash != tokens["refresh_token"]
    assert stored.token_hash == stack.tokens.hash_refresh_token(tokens["refresh_token"])


def test_phone_value_object_is_stored(client: TestClient, stack: Stack) -> None:
    register(client)
    account = next(iter(stack.database.accounts.values()))
    assert account.phone == PhoneNumber(E164)
