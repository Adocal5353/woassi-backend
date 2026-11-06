import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from woassi.modules.shops.application.ports import MetaPhoneNumber
from woassi.modules.shops.application.use_cases.receiving_account import SetReceivingAccount
from woassi.modules.shops.application.use_cases.shops import (
    CheckShopOwnership,
    CreateShop,
    ResolveShopByPhoneNumber,
)
from woassi.modules.shops.application.use_cases.whatsapp import ConnectWhatsApp
from woassi.modules.shops.domain.errors import (
    InvalidReceivingAccount,
    PhoneNumberAlreadyConnected,
)
from woassi.modules.shops.domain.shop import (
    InvoiceDetails,
    Operator,
    PaymentMode,
    ShopSettings,
    ShopStatus,
    WhatsAppStatus,
)
from woassi.modules.shops.infrastructure.models import ShopModel, ShopSettingsModel
from woassi.modules.shops.infrastructure.uow import SqlAlchemyShopsUoW
from woassi.shared.domain.events import DomainEvent
from woassi.shared.domain.values import PhoneNumber
from woassi.shared.infrastructure.audit import AuditEntryModel
from woassi.shared.infrastructure.clock import FrozenClock
from woassi.shared.infrastructure.crypto import FernetSecretCipher
from woassi.shared.infrastructure.phone import PhonenumbersNormalizer

pytestmark = pytest.mark.integration

NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
TOKEN = "EAAG-business-token"
CIPHER = FernetSecretCipher([Fernet.generate_key().decode()])


class NullBus:
    async def publish(self, event: DomainEvent) -> None:
        return None


class StubMeta:
    """Yields once inside the Meta calls, so that two connections really overlap."""

    async def exchange_code(self, code: str) -> str:
        await asyncio.sleep(0.01)
        return TOKEN

    async def subscribe_app(self, waba_id: str, token: str) -> None:
        return None

    async def get_phone_number(self, phone_number_id: str, token: str) -> MetaPhoneNumber:
        return MetaPhoneNumber("+228 90 12 34 56", "Chez Ama", False, True)

    async def link_catalog(
        self, waba_id: str, phone_number_id: str, token: str, catalog_id: str | None
    ) -> str | None:
        return "3003"

    async def sync_business_app_data(self, phone_number_id: str, token: str) -> None:
        return None

    async def unsubscribe_app(self, waba_id: str, token: str) -> None:
        return None

    async def token_is_valid(self, token: str) -> bool:
        return True


def uow_of(sessions: async_sessionmaker[AsyncSession]) -> SqlAlchemyShopsUoW:
    return SqlAlchemyShopsUoW(sessions, NullBus(), FrozenClock(NOW))


class FakeImages:
    def public_url(self, key: str) -> str:
        return key


async def new_shop(
    sessions: async_sessionmaker[AsyncSession], account_id: UUID | None = None
) -> UUID:
    use_case = CreateShop(lambda: uow_of(sessions), FakeImages(), FrozenClock(NOW))  # type: ignore[arg-type]
    return (await use_case.execute(account_id=account_id or uuid4(), name="Chez Ama")).id


def connect(sessions: async_sessionmaker[AsyncSession]) -> ConnectWhatsApp:
    return ConnectWhatsApp(uow_of(sessions), StubMeta(), CIPHER, FrozenClock(NOW))


async def test_a_shop_gets_default_settings(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    shop_id = await new_shop(sessions)
    async with uow_of(sessions) as uow:
        shop = await uow.shops.get(shop_id)
    assert shop is not None
    assert shop.settings == ShopSettings()


async def test_aggregate_round_trip(sessions: async_sessionmaker[AsyncSession]) -> None:
    shop_id = await new_shop(sessions)
    settings = ShopSettings(
        notification_number=PhoneNumber("+22890123456"),
        payment_modes=(PaymentMode.CASH, PaymentMode.MOOV),
        welcome_message="Bienvenue",
        invoice_details=InvoiceDetails(company_name="Ama SARL", tax_id="1"),
        invoice_prefix="AMA",
    )
    async with uow_of(sessions) as uow:
        shop = await uow.shops.get(shop_id)
        assert shop is not None
        shop.settings = settings
        await uow.shops.save(shop)
        await uow.commit()

    async with uow_of(sessions) as uow:
        loaded = await uow.shops.get(shop_id)
    assert loaded is not None
    assert loaded.settings == settings


async def test_same_name_gets_a_new_slug(sessions: async_sessionmaker[AsyncSession]) -> None:
    first, second = await new_shop(sessions), await new_shop(sessions)
    async with sessions() as session:
        slugs = list(await session.scalars(select(ShopModel.slug)))
    assert first != second
    assert len(set(slugs)) == 2


async def test_concurrent_creations_with_one_name(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await asyncio.gather(*(new_shop(sessions) for _ in range(5)))
    async with sessions() as session:
        slugs = list(await session.scalars(select(ShopModel.slug)))
    assert len(set(slugs)) == 5


async def test_connect_and_resolve(sessions: async_sessionmaker[AsyncSession]) -> None:
    shop_id = await new_shop(sessions)

    view = await connect(sessions).execute(
        shop_id=shop_id, code="code", waba_id="1", phone_number_id="2"
    )

    assert view.status is WhatsAppStatus.CONNECTED
    async with uow_of(sessions) as uow:
        shop = await uow.shops.get(shop_id)
    assert shop is not None and shop.status is ShopStatus.ACTIVE
    resolved = await ResolveShopByPhoneNumber(uow_of(sessions), CIPHER).execute("2")
    assert resolved is not None
    assert (resolved.shop_id, resolved.access_token) == (shop_id, TOKEN)


async def test_the_database_keeps_one_shop_per_number(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Both pass the first check, as neither has saved yet: only the constraint can decide."""
    first, second = await new_shop(sessions), await new_shop(sessions)

    results = await asyncio.gather(
        *(
            connect(sessions).execute(shop_id=shop, code="c", waba_id="1", phone_number_id="2")
            for shop in (first, second)
        ),
        return_exceptions=True,
    )

    errors = [result for result in results if isinstance(result, Exception)]
    assert len(errors) == 1
    assert isinstance(errors[0], PhoneNumberAlreadyConnected)

    async with uow_of(sessions) as uow:
        statuses = [(await uow.shops.get(shop)) for shop in (first, second)]
    connected = [s for s in statuses if s is not None and s.whatsapp_connected]
    failed = [s for s in statuses if s is not None and not s.whatsapp_connected]
    assert len(connected) == len(failed) == 1
    assert failed[0].whatsapp is not None
    assert failed[0].whatsapp.status is WhatsAppStatus.ERROR
    assert failed[0].status is ShopStatus.DRAFT


async def test_ownership_ignores_archived_shops(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    owner = uuid4()
    shop_id = await new_shop(sessions, owner)
    check = CheckShopOwnership(uow_of(sessions))

    assert await check.execute(account_id=owner, shop_id=shop_id)
    assert not await check.execute(account_id=uuid4(), shop_id=shop_id)

    async with uow_of(sessions) as uow:
        shop = await uow.shops.get(shop_id)
        assert shop is not None
        shop.archive(NOW)
        await uow.shops.save(shop)
        await uow.commit()

    assert not await check.execute(account_id=owner, shop_id=shop_id)
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ShopSettingsModel)) == 1


async def test_receiving_account_and_audit_share_a_transaction(
    sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    shop_id = await new_shop(sessions)
    use_case = SetReceivingAccount(uow_of(sessions), PhonenumbersNormalizer(), CIPHER)

    async def failing_commit(self: object) -> None:
        raise InvalidReceivingAccount("The commit failed.")

    monkeypatch.setattr(SqlAlchemyShopsUoW, "commit", failing_commit)
    with pytest.raises(InvalidReceivingAccount):
        await use_case.execute(
            shop_id=shop_id,
            account_id=uuid4(),
            operator=Operator.MIXX,
            number="90 12 34 56",
            holder_name="Ama",
        )
    monkeypatch.undo()

    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(AuditEntryModel)) == 0
    async with uow_of(sessions) as uow:
        shop = await uow.shops.get(shop_id)
    assert shop is not None and shop.receiving_account is None
