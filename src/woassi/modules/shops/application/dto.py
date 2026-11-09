from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from woassi.modules.shops.domain.shop import (
    InvoiceDetails,
    Operator,
    PaymentMode,
    ReceivingAccount,
    Shop,
    ShopSettings,
    ShopStatus,
    WhatsAppAccount,
    WhatsAppStatus,
)
from woassi.shared.application.ports import SecretCipher, StoragePort


@dataclass(frozen=True, slots=True)
class ShopView:
    id: UUID
    name: str
    slug: str
    category: str
    city: str
    address: str
    status: ShopStatus
    logo_url: str | None
    created_at: datetime


def shop_view(shop: Shop, images: StoragePort) -> ShopView:
    return ShopView(
        id=shop.id,
        name=shop.name,
        slug=shop.slug,
        category=shop.category,
        city=shop.city,
        address=shop.address,
        status=shop.status,
        logo_url=images.public_url(shop.logo_key) if shop.logo_key else None,
        created_at=shop.created_at,
    )


@dataclass(frozen=True, slots=True)
class SettingsView:
    notification_number: str | None
    payment_modes: tuple[PaymentMode, ...]
    reminder_1_minutes: int
    reminder_2_minutes: int
    expiration_hours: int
    welcome_message: str
    invoice_details: InvoiceDetails
    invoice_prefix: str


def settings_view(settings: ShopSettings) -> SettingsView:
    number = settings.notification_number
    return SettingsView(
        notification_number=number.value if number else None,
        payment_modes=settings.payment_modes,
        reminder_1_minutes=settings.reminder_1_minutes,
        reminder_2_minutes=settings.reminder_2_minutes,
        expiration_hours=settings.expiration_hours,
        welcome_message=settings.welcome_message,
        invoice_details=settings.invoice_details,
        invoice_prefix=settings.invoice_prefix,
    )


@dataclass(frozen=True, slots=True)
class WhatsAppView:
    """No token here, encrypted or not."""

    status: WhatsAppStatus
    waba_id: str
    phone_number_id: str | None
    display_phone_number: str | None
    verified_name: str | None
    catalog_id: str | None
    connected_at: datetime | None
    error_message: str | None


def whatsapp_view(account: WhatsAppAccount) -> WhatsAppView:
    return WhatsAppView(
        status=account.status,
        waba_id=account.waba_id,
        phone_number_id=account.phone_number_id,
        display_phone_number=account.display_phone_number,
        verified_name=account.verified_name,
        catalog_id=account.catalog_id,
        connected_at=account.connected_at,
        error_message=account.error_message,
    )


@dataclass(frozen=True, slots=True)
class ReceivingAccountView:
    operator: Operator
    number: str
    holder_name: str
    aggregator_merchant_id: str | None
    verified: bool


def receiving_account_view(account: ReceivingAccount, cipher: SecretCipher) -> ReceivingAccountView:
    encrypted = account.encrypted_merchant_id
    return ReceivingAccountView(
        operator=account.operator,
        number=account.number.value,
        holder_name=account.holder_name,
        aggregator_merchant_id=cipher.decrypt(encrypted) if encrypted else None,
        verified=account.verified,
    )


@dataclass(frozen=True, slots=True)
class LogoUpload:
    logo_id: UUID
    upload_url: str
    expire_s: int


@dataclass(frozen=True, slots=True)
class ShopRouting:
    shop_id: UUID
    phone_number_id: str
    access_token: str = field(repr=False)
