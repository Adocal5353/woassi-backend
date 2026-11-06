from collections.abc import Iterator

import httpx
import pytest
from minio import Minio
from testcontainers.community.minio import MinioContainer

from woassi.shared.domain.errors import ObjectNotFound
from woassi.shared.infrastructure.storage.minio_storage import BucketNotPublic, MinioStorage

pytestmark = pytest.mark.integration

BUCKET = "test-bucket"
REGION = "us-east-1"


@pytest.fixture(scope="module")
def minio_client() -> Iterator[Minio]:
    # /tmp/data: the image runs without root privileges.
    container = MinioContainer(
        image="cgr.dev/chainguard/minio:latest",
        access_key="testaccess",
        secret_key="testsecret",
    ).with_command("server /tmp/data")
    with container:
        endpoint = f"{container.get_container_host_ip()}:{container.get_exposed_port(9000)}"
        client = Minio(
            endpoint,
            access_key="testaccess",
            secret_key="testsecret",
            secure=False,
            region=REGION,
        )
        client.make_bucket(BUCKET)
        yield client


@pytest.fixture
def storage(minio_client: Minio) -> MinioStorage:
    return MinioStorage(minio_client, minio_client, BUCKET)


async def test_put_stat_get_delete(storage: MinioStorage) -> None:
    await storage.put("a/b.txt", b"content", "text/plain")

    info = await storage.stat("a/b.txt")
    assert info is not None
    assert info.size == 7
    assert info.content_type == "text/plain"
    assert await storage.get("a/b.txt") == b"content"

    await storage.delete("a/b.txt")
    assert await storage.stat("a/b.txt") is None


async def test_missing_object(storage: MinioStorage) -> None:
    assert await storage.stat("absent") is None
    with pytest.raises(ObjectNotFound):
        await storage.get("absent")


async def test_presigned_put_then_get(storage: MinioStorage) -> None:
    async with httpx.AsyncClient() as http:
        url_put = await storage.presigned_put("presigned.bin", "image/png", 60)
        assert (await http.put(url_put, content=b"bytes")).status_code == 200

        url_get = await storage.presigned_get("presigned.bin", 60)
        response = await http.get(url_get)
    assert response.status_code == 200
    assert response.content == b"bytes"


async def test_signing_uses_public_endpoint(minio_client: Minio) -> None:
    signer = Minio(
        "images.woassi.test",
        access_key="testaccess",
        secret_key="testsecret",
        secure=True,
        region=REGION,
    )
    storage = MinioStorage(minio_client, signer, BUCKET)
    assert (await storage.presigned_get("x")).startswith(f"https://images.woassi.test/{BUCKET}/x?")


def test_public_url(minio_client: Minio) -> None:
    public = MinioStorage(minio_client, minio_client, BUCKET, public_base_url="http://cdn/b/")
    assert public.public_url("a.webp") == "http://cdn/b/a.webp"

    with pytest.raises(BucketNotPublic):
        MinioStorage(minio_client, minio_client, BUCKET).public_url("a.webp")
