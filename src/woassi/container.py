"""Composition root: the only place where ports are bound to their adapters."""

from dataclasses import dataclass

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from minio import Minio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from woassi.config import Settings
from woassi.integration.accounts import AccountsAuthenticator
from woassi.integration.shops import DenyAllShopOwnership
from woassi.modules.accounts.application.facade import AccountsUseCases
from woassi.modules.accounts.application.ports import (
    AccountsUnitOfWork,
    PasswordHasher,
    TokenService,
    VerificationCodeSender,
)
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
from woassi.modules.accounts.infrastructure.code_sender import LogVerificationCodeSender
from woassi.modules.accounts.infrastructure.security import Argon2PasswordHasher, JwtTokenService
from woassi.modules.accounts.infrastructure.uow import SqlAlchemyAccountsUoW
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
from woassi.shared.application.audit import ListAuditEntries
from woassi.shared.application.facade import SharedUseCases
from woassi.shared.application.ports import (
    AccountAuthenticator,
    Clock,
    IdempotencyStore,
    PhoneNormalizer,
    RateLimiter,
    SecretCipher,
    ShopOwnershipPort,
    StoragePort,
    UnitOfWork,
)
from woassi.shared.application.readiness import CheckReadiness
from woassi.shared.infrastructure.clock import SystemClock
from woassi.shared.infrastructure.crypto import FernetSecretCipher
from woassi.shared.infrastructure.db.session import create_engine, create_session_factory
from woassi.shared.infrastructure.db.uow import SqlAlchemyUnitOfWork
from woassi.shared.infrastructure.events.arq_dispatcher import ArqDeferredDispatcher
from woassi.shared.infrastructure.events.bus import InProcessEventBus
from woassi.shared.infrastructure.health import minio_check, postgres_check, redis_check
from woassi.shared.infrastructure.idempotency import RedisIdempotencyStore
from woassi.shared.infrastructure.phone import PhonenumbersNormalizer
from woassi.shared.infrastructure.rate_limiter import RedisRateLimiter
from woassi.shared.infrastructure.storage.minio_storage import MinioStorage


def _minio_client(endpoint: str, settings: Settings) -> Minio:
    return Minio(
        endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
        region=settings.minio_region,
    )


def _code_sender(settings: Settings) -> VerificationCodeSender:
    # The log sender writes codes in clear text: it must never run outside development.
    if settings.app_env == "dev":
        return LogVerificationCodeSender()
    raise RuntimeError(f"No verification code sender for environment {settings.app_env}.")


@dataclass
class Container(AccountsUseCases, CatalogUseCases, MessagingUseCases, SharedUseCases):
    settings: Settings
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    arq: ArqRedis
    minio: Minio
    clock: Clock
    event_bus: InProcessEventBus
    cipher: SecretCipher
    hasher: PasswordHasher
    code_sender: VerificationCodeSender
    uploads: StoragePort
    product_images: StoragePort
    documents: StoragePort

    @classmethod
    async def build(cls, settings: Settings) -> "Container":
        engine = create_engine(settings.database_url)
        client = _minio_client(settings.minio_endpoint, settings)
        signer = _minio_client(settings.minio_public_endpoint, settings)
        arq = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        container = cls(
            settings=settings,
            engine=engine,
            sessions=create_session_factory(engine),
            arq=arq,
            minio=client,
            clock=SystemClock(),
            event_bus=InProcessEventBus(ArqDeferredDispatcher(arq)),
            cipher=FernetSecretCipher(settings.encryption_keys),
            hasher=Argon2PasswordHasher(),
            code_sender=_code_sender(settings),
            uploads=MinioStorage(client, signer, settings.minio_bucket_uploads),
            product_images=MinioStorage(
                client,
                signer,
                settings.minio_bucket_products,
                public_base_url=settings.public_images_base_url,
            ),
            documents=MinioStorage(client, signer, settings.minio_bucket_documents),
        )
        container._register_subscribers()
        return container

    def _register_subscribers(self) -> None:
        """Bind domain events to their subscribers, in the API and in the worker alike."""

    async def close(self) -> None:
        await self.arq.aclose()
        await self.engine.dispose()

    # Factories
    def unit_of_work(self) -> UnitOfWork:
        return SqlAlchemyUnitOfWork(self.sessions, self.event_bus, self.clock)

    def accounts_uow(self) -> AccountsUnitOfWork:
        return SqlAlchemyAccountsUoW(self.sessions, self.event_bus, self.clock)

    def rate_limiter(self) -> RateLimiter:
        return RedisRateLimiter(self.arq)

    def token_service(self) -> TokenService:
        return JwtTokenService(self.settings.jwt_secret, self.settings.jwt_access_ttl, self.clock)

    def account_authenticator(self) -> AccountAuthenticator:
        return AccountsAuthenticator(self.authenticate_account())

    def shop_ownership(self) -> ShopOwnershipPort:
        return DenyAllShopOwnership()

    def catalog_uow(self) -> CatalogUnitOfWork:
        return SqlAlchemyCatalogUoW(self.sessions, self.event_bus, self.clock)

    def phone_normalizer(self) -> PhoneNormalizer:
        return PhonenumbersNormalizer()

    def idempotency_store(self) -> IdempotencyStore:
        return RedisIdempotencyStore(self.arq)

    def photo_jobs(self) -> PhotoJobQueue:
        return ArqPhotoJobQueue(self.arq)

    def image_processor(self) -> ImageProcessor:
        return PillowImageProcessor()

    def meta_events(self) -> EventQueue:
        return ArqEventQueue(self.arq)

    # Use cases: accounts
    def register(self) -> Register:
        return Register(
            self.accounts_uow(),
            self.hasher,
            self.code_sender,
            self.rate_limiter(),
            self.phone_normalizer(),
            self.clock,
        )

    def verify_phone(self) -> VerifyPhone:
        return VerifyPhone(self.accounts_uow(), self.hasher, self.phone_normalizer(), self.clock)

    def login(self) -> Login:
        return Login(
            self.accounts_uow(),
            self.hasher,
            self.token_service(),
            self.rate_limiter(),
            self.phone_normalizer(),
            self.clock,
            refresh_ttl_s=self.settings.jwt_refresh_ttl,
        )

    def refresh_tokens(self) -> RefreshTokens:
        return RefreshTokens(
            self.accounts_uow(),
            self.token_service(),
            self.clock,
            refresh_ttl_s=self.settings.jwt_refresh_ttl,
        )

    def logout(self) -> Logout:
        return Logout(self.accounts_uow(), self.token_service(), self.clock)

    def logout_everywhere(self) -> LogoutEverywhere:
        return LogoutEverywhere(self.accounts_uow(), self.clock)

    def request_password_reset(self) -> RequestPasswordReset:
        return RequestPasswordReset(
            self.accounts_uow(),
            self.hasher,
            self.code_sender,
            self.rate_limiter(),
            self.phone_normalizer(),
            self.clock,
        )

    def reset_password(self) -> ResetPassword:
        return ResetPassword(self.accounts_uow(), self.hasher, self.phone_normalizer(), self.clock)

    def get_my_account(self) -> GetMyAccount:
        return GetMyAccount(self.accounts_uow())

    def update_my_account(self) -> UpdateMyAccount:
        return UpdateMyAccount(self.accounts_uow())

    def change_password(self) -> ChangePassword:
        return ChangePassword(self.accounts_uow(), self.hasher, self.rate_limiter(), self.clock)

    def authenticate_account(self) -> AuthenticateAccount:
        return AuthenticateAccount(self.accounts_uow(), self.token_service())

    # Use cases: shared
    def list_audit_entries(self) -> ListAuditEntries:
        return ListAuditEntries(self.unit_of_work())

    def check_readiness(self) -> CheckReadiness:
        return CheckReadiness(
            {
                "postgres": postgres_check(self.engine),
                "redis": redis_check(self.arq),
                "minio": minio_check(self.minio, self.settings.minio_bucket_uploads),
            }
        )

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
