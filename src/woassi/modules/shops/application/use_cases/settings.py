from uuid import UUID

from woassi.modules.shops.application.dto import SettingsView, settings_view
from woassi.modules.shops.application.ports import ShopsUnitOfWork
from woassi.modules.shops.application.use_cases.support import load_shop
from woassi.modules.shops.domain.shop import InvoiceDetails, PaymentMode, ShopSettings
from woassi.shared.application.ports import PhoneNormalizer


class GetSettings:
    def __init__(self, uow: ShopsUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, shop_id: UUID) -> SettingsView:
        async with self._uow as uow:
            shop = await load_shop(uow, shop_id)
        return settings_view(shop.settings)


class ReplaceSettings:
    def __init__(self, uow: ShopsUnitOfWork, phones: PhoneNormalizer) -> None:
        self._uow = uow
        self._phones = phones

    async def execute(
        self,
        *,
        shop_id: UUID,
        notification_number: str | None,
        payment_modes: tuple[PaymentMode, ...],
        reminder_1_minutes: int,
        reminder_2_minutes: int,
        expiration_hours: int,
        welcome_message: str,
        invoice_details: InvoiceDetails,
        invoice_prefix: str,
    ) -> SettingsView:
        settings = ShopSettings(
            notification_number=(
                self._phones.normalize(notification_number) if notification_number else None
            ),
            payment_modes=payment_modes,
            reminder_1_minutes=reminder_1_minutes,
            reminder_2_minutes=reminder_2_minutes,
            expiration_hours=expiration_hours,
            welcome_message=welcome_message,
            invoice_details=invoice_details,
            invoice_prefix=invoice_prefix,
        )
        async with self._uow as uow:
            shop = await load_shop(uow, shop_id)
            shop.settings = settings
            await uow.shops.save(shop)
            await uow.commit()
        return settings_view(settings)
