from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from woassi.modules.accounts.domain.account import Account, validate_password
from woassi.modules.accounts.domain.errors import AccountSuspended, InvalidAccount, WeakPassword
from woassi.modules.accounts.domain.events import AccountCreated, AccountLoggedIn
from woassi.modules.accounts.domain.refresh_token import RefreshToken
from woassi.modules.accounts.domain.verification_code import (
    MAX_ATTEMPTS,
    CodePurpose,
    VerificationCode,
    generate_code,
)
from woassi.shared.domain.values import PhoneNumber

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def account() -> Account:
    return Account.register(
        full_name=" Ama Mensah ",
        phone=PhoneNumber("+22890123456"),
        password_hash="hash",
        now=NOW,
    )


def test_register_starts_active_and_unverified() -> None:
    created = account()
    assert created.full_name == "Ama Mensah"
    assert created.is_active
    assert not created.phone_verified
    assert [type(event) for event in created.pull_events()] == [AccountCreated]


def test_name_is_required() -> None:
    with pytest.raises(InvalidAccount):
        account().rename("  ")


@pytest.mark.parametrize("password", ["", "1234567", "x" * 129])
def test_rejects_bad_passwords(password: str) -> None:
    with pytest.raises(WeakPassword):
        validate_password(password)


@pytest.mark.parametrize("password", ["12345678", "x" * 128])
def test_accepts_good_passwords(password: str) -> None:
    validate_password(password)


def test_login_is_recorded() -> None:
    logged_in = account()
    logged_in.pull_events()
    logged_in.record_login(NOW)
    assert logged_in.last_login_at == NOW
    assert [type(event) for event in logged_in.pull_events()] == [AccountLoggedIn]


def test_suspended_account_cannot_log_in() -> None:
    suspended = account()
    suspended.pull_events()
    suspended.suspend()
    with pytest.raises(AccountSuspended):
        suspended.record_login(NOW)
    assert suspended.last_login_at is None
    assert suspended.pull_events() == []


def test_secrets_stay_out_of_repr() -> None:
    assert "hash" not in repr(account()).replace("password_hash", "")


def code() -> VerificationCode:
    return VerificationCode.issue(
        account_id=uuid4(), purpose=CodePurpose.PASSWORD_RESET, code_hash="h", now=NOW
    )


def test_codes_have_six_digits() -> None:
    assert all(len(c) == 6 and c.isdigit() for c in (generate_code() for _ in range(100)))


def test_code_lasts_ten_minutes() -> None:
    assert code().is_usable(NOW + timedelta(minutes=9, seconds=59))
    assert not code().is_usable(NOW + timedelta(minutes=10))


def test_code_allows_five_attempts() -> None:
    limited = code()
    for _ in range(MAX_ATTEMPTS - 1):
        limited.record_failure()
    assert limited.is_usable(NOW)
    limited.record_failure()
    assert not limited.is_usable(NOW)


def test_consumed_code_cannot_be_reused() -> None:
    used = code()
    used.consume(NOW)
    assert not used.is_usable(NOW)


def refresh(**fields: object) -> RefreshToken:
    return RefreshToken(
        id=uuid4(),
        account_id=uuid4(),
        family_id=uuid4(),
        token_hash="h",
        expires_at=NOW + timedelta(days=1),
        **fields,  # type: ignore[arg-type]
    )


def test_refresh_token_usability() -> None:
    assert refresh().is_usable(NOW)
    assert not refresh().is_usable(NOW + timedelta(days=2))
    assert not refresh(revoked_at=NOW).is_usable(NOW)


def test_a_consumed_refresh_token_stays_visible_so_that_reuse_is_detected() -> None:
    assert refresh(consumed_at=NOW).is_usable(NOW + timedelta(days=2))
