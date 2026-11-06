import pytest

from woassi.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
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
        woassi_encryption_key="not-used-without-the-container",
    )
