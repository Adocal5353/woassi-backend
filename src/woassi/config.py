from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"

    database_url: str
    redis_url: str

    minio_endpoint: str
    minio_public_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_secure: bool = False
    minio_region: str = "us-east-1"
    minio_bucket_uploads: str = "woassi-uploads"
    minio_bucket_products: str = "woassi-products"
    minio_bucket_documents: str = "woassi-documents"
    public_images_base_url: str

    # min_length=1: an empty secret would let anyone forge the HMAC signature.
    meta_app_secret: str = Field(min_length=1)
    meta_verify_token: str = Field(min_length=1)
    meta_graph_version: str = "v24.0"

    sentry_dsn: str | None = None
    cors_origins: Annotated[list[str], NoDecode] = []

    max_photos_per_product: int = 5
    photo_max_size_bytes: int = 8 * 1024 * 1024

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # values read from the environment
