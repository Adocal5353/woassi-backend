from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.fakes import FakeJobQueue, FakeStorage, FakeUoW
from woassi.config import Settings
from woassi.main import create_app
from woassi.modules.catalog.api.deps import get_catalog
from woassi.modules.catalog.application.use_cases.photos import (
    ConfirmPhoto,
    RequestPhotoUpload,
)
from woassi.modules.catalog.application.use_cases.products import (
    CreateProduct,
    GetProduct,
    ListProducts,
)


class FakeCatalog:
    def __init__(self) -> None:
        self.uow = FakeUoW()
        self.uploads = FakeStorage()
        self.images = FakeStorage("http://images")
        self.jobs = FakeJobQueue()

    def create_product(self) -> CreateProduct:
        return CreateProduct(self.uow, self.images)

    def list_products(self) -> ListProducts:
        return ListProducts(self.uow, self.images)

    def get_product(self) -> GetProduct:
        return GetProduct(self.uow, self.images)

    def request_photo_upload(self) -> RequestPhotoUpload:
        return RequestPhotoUpload(self.uow, self.uploads)

    def confirm_photo(self) -> ConfirmPhoto:
        return ConfirmPhoto(self.uow, self.uploads, self.jobs)


@pytest.fixture
def catalog() -> FakeCatalog:
    return FakeCatalog()


@pytest.fixture
def client(settings: Settings, catalog: FakeCatalog) -> TestClient:
    app = create_app(settings)
    app.dependency_overrides[get_catalog] = lambda: catalog
    return TestClient(app)


PRODUCT = {"name": "Pagne", "price": 5000, "stock": 3, "retailer_id": "SKU-1"}


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_create_list_get(client: TestClient) -> None:
    base = f"/shops/{uuid4()}/products"

    created = client.post(base, json=PRODUCT)
    assert created.status_code == 201
    assert created.json()["price"] == 5000
    assert created.json()["photos"] == []

    assert client.get(base).json() == [created.json()]
    assert client.get(f"{base}/{created.json()['id']}").json() == created.json()


def test_product_not_found_returns_code_and_message(client: TestClient) -> None:
    response = client.get(f"/shops/{uuid4()}/products/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["code"] == "catalog.product_not_found"
    assert response.json().keys() == {"code", "message"}


def test_name_empty_after_strip(client: TestClient) -> None:
    response = client.post(f"/shops/{uuid4()}/products", json={**PRODUCT, "name": "   "})
    assert response.status_code == 422
    assert response.json()["code"] == "catalog.invalid_product"


@pytest.mark.parametrize("field", [{"price": -1}, {"price": 10.5}, {"stock": -1}])
def test_schema_validation(client: TestClient, field: dict[str, float]) -> None:
    response = client.post(f"/shops/{uuid4()}/products", json={**PRODUCT, **field})
    assert response.status_code == 422


def test_photo_upload_flow(client: TestClient, catalog: FakeCatalog) -> None:
    base = f"/shops/{uuid4()}/products"
    product_id = client.post(base, json=PRODUCT).json()["id"]

    upload = client.post(
        f"{base}/{product_id}/photos/upload-url",
        json={"content_type": "image/jpeg", "size": 1000},
    )
    assert upload.status_code == 200
    photo_id = upload.json()["photo_id"]

    # The file has not been sent to storage yet
    confirm_url = f"{base}/{product_id}/photos/{photo_id}/confirm"
    assert client.post(confirm_url).status_code == 422

    product = next(iter(catalog.uow.repository.products.values()))
    catalog.uploads.objects[product.photos[0].original_key] = b"image"
    assert client.post(confirm_url).status_code == 202
    assert [str(p) for p in catalog.jobs.photos] == [photo_id]


def test_too_many_photos_is_a_conflict(client: TestClient) -> None:
    base = f"/shops/{uuid4()}/products"
    product_id = client.post(base, json=PRODUCT).json()["id"]
    body = {"content_type": "image/jpeg", "size": 1000}
    for _ in range(5):
        assert client.post(f"{base}/{product_id}/photos/upload-url", json=body).status_code == 200

    response = client.post(f"{base}/{product_id}/photos/upload-url", json=body)
    assert response.status_code == 409
    assert response.json()["code"] == "catalog.too_many_photos"
