from woassi.shared.domain.errors import Conflict, Forbidden, InvalidData, Unauthorized


class InvalidCredentials(Unauthorized):
    """Deliberately vague: it must not reveal whether the phone number exists."""

    code = "auth.invalid_credentials"


class InvalidRefreshToken(Unauthorized):
    code = "auth.invalid_refresh_token"


class AccountSuspended(Forbidden):
    code = "accounts.suspended"


class PhoneAlreadyUsed(Conflict):
    code = "accounts.phone_already_used"


class InvalidAccount(InvalidData):
    code = "accounts.invalid_account"


class WeakPassword(InvalidData):
    code = "accounts.weak_password"


class WrongPassword(InvalidData):
    code = "accounts.wrong_password"


class InvalidCode(InvalidData):
    """Same error for a wrong, expired or exhausted code, or an unknown phone number."""

    code = "accounts.invalid_code"
