import hashlib
import hmac

from woassi.modules.messaging.application.signature import is_valid_signature

SECRET = "app-secret"
BODY = b'{"object":"whatsapp_business_account"}'


def sign(body: bytes = BODY, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature() -> None:
    assert is_valid_signature(BODY, sign(), SECRET)


def test_modified_body() -> None:
    assert not is_valid_signature(BODY + b" ", sign(), SECRET)


def test_wrong_secret() -> None:
    assert not is_valid_signature(BODY, sign(secret="autre"), SECRET)


def test_missing_or_malformed_header() -> None:
    assert not is_valid_signature(BODY, None, SECRET)
    assert not is_valid_signature(BODY, "", SECRET)
    assert not is_valid_signature(BODY, sign().removeprefix("sha256="), SECRET)
    assert not is_valid_signature(BODY, "sha1=abc", SECRET)


def test_non_ascii_header_does_not_raise() -> None:
    assert not is_valid_signature(BODY, "sha256=é", SECRET)
