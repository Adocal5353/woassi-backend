from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from woassi.modules.shops.application.dto import (
    LogoUpload,
    ReceivingAccountView,
    SettingsView,
    ShopView,
    WhatsAppView,
)
from woassi.modules.shops.domain.shop import (
    InvoiceDetails,
    Language,
    Operator,
    PaymentMode,
    ShopStatus,
    ValidationMode,
    WhatsAppStatus,
)

# Meta ids end up in Graph API URL paths: digits only, so that none can rewrite the path.
META_ID = r"^\d{1,32}$"


class ShopCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(default="", max_length=100)
    city: str = Field(default="", max_length=100)
    address: str = Field(default="", max_length=300)


class ShopUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=300)


class ShopResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    category: str
    city: str
    address: str
    status: ShopStatus
    logo_url: str | None
    created_at: datetime

    @classmethod
    def from_view(cls, view: ShopView) -> "ShopResponse":
        return cls(
            id=view.id,
            name=view.name,
            slug=view.slug,
            category=view.category,
            city=view.city,
            address=view.address,
            status=view.status,
            logo_url=view.logo_url,
            created_at=view.created_at,
        )


class InvoiceDetailsBody(BaseModel):
    company_name: str = Field(default="", max_length=200)
    tax_id: str = Field(default="", max_length=50, description="NIF")
    trade_register: str = Field(default="", max_length=50, description="RCCM")
    address: str = Field(default="", max_length=300)
    phone: str = Field(default="", max_length=30)


class SettingsBody(BaseModel):
    notification_number: str | None = Field(default=None, max_length=30)
    payment_modes: tuple[PaymentMode, ...] = (PaymentMode.CASH,)
    reminder_1_minutes: int = Field(default=15, ge=1, le=10_000)
    reminder_2_minutes: int = Field(default=60, ge=1, le=10_000)
    expiration_hours: int = Field(default=24, ge=1, le=720)
    welcome_message: str = Field(default="", max_length=1024)
    invoice_details: InvoiceDetailsBody = InvoiceDetailsBody()
    invoice_prefix: str = "FAC"
    language: Language = Language.FR
    validation_mode: ValidationMode = ValidationMode.MANUAL
    auto_validation_max_amount: int | None = Field(default=None, ge=1, le=1_000_000_000_000)

    @classmethod
    def from_view(cls, view: SettingsView) -> "SettingsBody":
        details = view.invoice_details
        return cls(
            notification_number=view.notification_number,
            payment_modes=view.payment_modes,
            reminder_1_minutes=view.reminder_1_minutes,
            reminder_2_minutes=view.reminder_2_minutes,
            expiration_hours=view.expiration_hours,
            welcome_message=view.welcome_message,
            invoice_details=InvoiceDetailsBody(
                company_name=details.company_name,
                tax_id=details.tax_id,
                trade_register=details.trade_register,
                address=details.address,
                phone=details.phone,
            ),
            invoice_prefix=view.invoice_prefix,
            language=view.language,
            validation_mode=view.validation_mode,
            auto_validation_max_amount=view.auto_validation_max_amount,
        )

    def to_arguments(self) -> dict[str, object]:
        arguments = self.model_dump(exclude={"invoice_details"})
        arguments["invoice_details"] = InvoiceDetails(**self.invoice_details.model_dump())
        return arguments


class WhatsAppConnect(BaseModel):
    code: str = Field(min_length=1, max_length=2048)
    waba_id: str = Field(pattern=META_ID)
    phone_number_id: str = Field(pattern=META_ID)
    catalog_id: str | None = Field(
        default=None,
        pattern=META_ID,
        description="From `catalog_ids` in the Embedded Signup event, if the merchant chose one",
    )


class WhatsAppResponse(BaseModel):
    status: WhatsAppStatus
    waba_id: str
    phone_number_id: str | None
    display_phone_number: str | None
    verified_name: str | None
    catalog_id: str | None
    connected_at: datetime | None
    error_message: str | None

    @classmethod
    def from_view(cls, view: WhatsAppView) -> "WhatsAppResponse":
        return cls(
            status=view.status,
            waba_id=view.waba_id,
            phone_number_id=view.phone_number_id,
            display_phone_number=view.display_phone_number,
            verified_name=view.verified_name,
            catalog_id=view.catalog_id,
            connected_at=view.connected_at,
            error_message=view.error_message,
        )


class ReceivingAccountBody(BaseModel):
    operator: Operator
    number: str = Field(min_length=1, max_length=30)
    holder_name: str = Field(min_length=1, max_length=200)
    aggregator_merchant_id: str | None = Field(default=None, max_length=200)


class ReceivingAccountResponse(ReceivingAccountBody):
    verified: bool

    @classmethod
    def from_view(cls, view: ReceivingAccountView) -> "ReceivingAccountResponse":
        return cls(
            operator=view.operator,
            number=view.number,
            holder_name=view.holder_name,
            aggregator_merchant_id=view.aggregator_merchant_id,
            verified=view.verified,
        )


class LogoUploadRequest(BaseModel):
    content_type: str = Field(max_length=100)
    size: int = Field(description="Declared size in bytes")


class LogoUploadResponse(BaseModel):
    logo_id: UUID
    upload_url: str
    expire_s: int

    @classmethod
    def from_upload(cls, upload: LogoUpload) -> "LogoUploadResponse":
        return cls(logo_id=upload.logo_id, upload_url=upload.upload_url, expire_s=upload.expire_s)


class LogoConfirm(BaseModel):
    logo_id: UUID
