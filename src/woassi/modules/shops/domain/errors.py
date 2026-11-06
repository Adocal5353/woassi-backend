from woassi.shared.domain.errors import Conflict, InvalidData, UpstreamError


class InvalidShop(InvalidData):
    code = "shops.invalid_shop"


class InvalidSettings(InvalidData):
    code = "shops.invalid_settings"


class InvalidReceivingAccount(InvalidData):
    code = "shops.invalid_receiving_account"


class InvalidLogo(InvalidData):
    code = "shops.invalid_logo"


class ShopNotActivatable(Conflict):
    code = "shops.not_activatable"


class SlugTaken(Conflict):
    code = "shops.slug_taken"


class WhatsAppAlreadyConnected(Conflict):
    code = "shops.whatsapp_already_connected"


class PhoneNumberAlreadyConnected(Conflict):
    code = "shops.phone_number_already_connected"


class WhatsAppNotFound(InvalidData):
    code = "shops.whatsapp_not_connected"


class InvalidSignupCode(InvalidData):
    code = "shops.invalid_signup_code"


class PhoneNumberNotUsable(InvalidData):
    code = "shops.phone_number_not_usable"


class WhatsAppConnectionFailed(UpstreamError):
    code = "shops.whatsapp_connection_failed"
