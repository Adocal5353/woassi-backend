from typing import Any

import pytest
from pydantic import ValidationError

from woassi.config import Settings


def settings(**overrides: Any) -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://u:p@localhost/test",
        redis_url="redis://localhost:6379/0",
        minio_endpoint="localhost:9000",
        minio_public_endpoint="localhost:9000",
        minio_access_key="key",
        minio_secret_key="secret",
        public_images_base_url="http://localhost:9000/woassi-products",
        meta_app_secret="app-secret",
        meta_verify_token="verify-token",
        jwt_secret="test-secret-of-at-least-32-characters",
        **overrides,
    )


def test_single_key() -> None:
    assert settings(woassi_encryption_key="a").encryption_keys == ["a"]


def test_key_list_takes_precedence() -> None:
    configured = settings(woassi_encryption_key="a", woassi_encryption_keys="new, old")
    assert configured.encryption_keys == ["new", "old"]


@pytest.mark.parametrize("overrides", [{}, {"woassi_encryption_key": ""}])
def test_startup_fails_without_a_key(
    overrides: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("WOASSI_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("WOASSI_ENCRYPTION_KEYS", raising=False)
    with pytest.raises(ValidationError):
        settings(**overrides)
