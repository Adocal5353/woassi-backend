"""Composition root: the only place where ports are bound to their adapters."""

from dataclasses import dataclass

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from minio import Minio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from woassi.config import Settings
from woassi.modules.catalog.application.facade import CatalogUseCases
from woassi.modules.catalog.application.ports import (
    CatalogUnitOfWork,
    ImageProcessor,
    PhotoJobQueue,
)
from woassi.modules.catalog.application.use_cases.photos import (
    ConfirmPhoto,
    ProcessPhoto,
    RequestPhotoUpload,
)
from woassi.modules.catalog.application.use_cases.products import (
    CreateProduct,
    GetProduct,
    ListProducts,
)
from woassi.modules.catalog.infrastructure.image_processor import PillowImageProcessor
from woassi.modules.catalog.infrastructure.photo_queue import ArqPhotoJobQueue
from woassi.modules.catalog.infrastructure.uow import SqlAlchemyCatalogUoW
from woassi.modules.messaging.application.facade import MessagingUseCases
from woassi.modules.messaging.application.ports import EventQueue
from woassi.modules.messaging.application.use_cases.webhook import (
    ReceiveMetaWebhook,
    VerifyMetaSubscription,
)
from woassi.modules.messaging.infrastructure.event_queue import ArqEventQueue
from woassi.shared.application.ports import StoragePort
from woassi.shared.infrastructure.db.session import create_engine, create_session_factory
from woassi.shared.infrastructure.storage.minio_storage import MinioStorage


def _minio_client(endpoint: str, settings: Settings) -> Minio:
    return Minio(
        endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
        region=settings.minio_region,
    )


@dataclass
class Container(CatalogUseCases, MessagingUseCases):
    settings: Settings
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    arq: ArqRedis
    uploads: StoragePort
    product_images: StoragePort
    documents: StoragePort

    @classmethod
    async def build(cls, settings: Settings) -> "Container":
        engine = create_engine(settings.database_url)
        client = _minio_client(settings.minio_endpoint, settings)
        signer = _minio_client(settings.minio_public_endpoint, settings)
        return cls(
            settings=settings,
            engine=engine,
            sessions=create_session_factory(engine),
            arq=await create_pool(RedisSettings.from_dsn(settings.redis_url)),
            uploads=MinioStorage(client, signer, settings.minio_bucket_uploads),
            product_images=MinioStorage(
                client,
                signer,
                settings.minio_bucket_products,
                public_base_url=settings.public_images_base_url,
            ),
            documents=MinioStorage(client, signer, settings.minio_bucket_documents),
        )

    async def close(self) -> None:
        await self.arq.aclose()
        await self.engine.dispose()

    # Factories
    def catalog_uow(self) -> CatalogUnitOfWork:
        return SqlAlchemyCatalogUoW(self.sessions)

    def photo_jobs(self) -> PhotoJobQueue:
        return ArqPhotoJobQueue(self.arq)

    def image_processor(self) -> ImageProcessor:
        return PillowImageProcessor()

    def meta_events(self) -> EventQueue:
        return ArqEventQueue(self.arq)

    # Use cases: catalog
    def create_product(self) -> CreateProduct:
        return CreateProduct(self.catalog_uow(), self.product_images)

    def list_products(self) -> ListProducts:
        return ListProducts(self.catalog_uow(), self.product_images)

    def get_product(self) -> GetProduct:
        return GetProduct(self.catalog_uow(), self.product_images)

    def request_photo_upload(self) -> RequestPhotoUpload:
        return RequestPhotoUpload(
            self.catalog_uow(),
            self.uploads,
            max_photos=self.settings.max_photos_per_product,
            max_size_bytes=self.settings.photo_max_size_bytes,
        )

    def confirm_photo(self) -> ConfirmPhoto:
        return ConfirmPhoto(
            self.catalog_uow(),
            self.uploads,
            self.photo_jobs(),
            max_size_bytes=self.settings.photo_max_size_bytes,
        )

    def process_photo(self) -> ProcessPhoto:
        return ProcessPhoto(
            self.catalog_uow(), self.uploads, self.product_images, self.image_processor()
        )

    # Use cases: messaging
    def verify_meta_subscription(self) -> VerifyMetaSubscription:
        return VerifyMetaSubscription(self.settings.meta_verify_token)

    def receive_meta_webhook(self) -> ReceiveMetaWebhook:
        return ReceiveMetaWebhook(self.settings.meta_app_secret, self.meta_events())
