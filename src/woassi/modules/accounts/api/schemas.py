from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from woassi.modules.accounts.application.dto import AccountView, TokenPair
from woassi.modules.accounts.domain.account import AccountStatus

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
Phone = Field(min_length=1, max_length=30)
# Length rules live in the domain; this only bounds what reaches the password hasher.
Password = Field(max_length=1024)


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    phone: str = Phone
    password: str = Password
    email: str | None = Field(default=None, max_length=254, pattern=EMAIL_PATTERN)


class VerifyPhoneRequest(BaseModel):
    phone: str = Phone
    code: str = Field(max_length=6)


class LoginRequest(BaseModel):
    phone: str = Phone
    password: str = Password


class RefreshRequest(BaseModel):
    """Optional for browsers, which send the cookie instead."""

    refresh_token: str | None = Field(default=None, max_length=128)


class PasswordResetRequest(BaseModel):
    phone: str = Phone


class PasswordReset(BaseModel):
    phone: str = Phone
    code: str = Field(max_length=6)
    new_password: str = Password


class PasswordChange(BaseModel):
    current_password: str = Password
    new_password: str = Password


class AccountUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=254, pattern=EMAIL_PATTERN)


class AccountResponse(BaseModel):
    id: UUID
    full_name: str
    phone: str
    email: str | None
    status: AccountStatus
    phone_verified: bool
    created_at: datetime
    last_login_at: datetime | None

    @classmethod
    def from_view(cls, view: AccountView) -> "AccountResponse":
        return cls(
            id=view.id,
            full_name=view.full_name,
            phone=view.phone,
            email=view.email,
            status=view.status,
            phone_verified=view.phone_verified,
            created_at=view.created_at,
            last_login_at=view.last_login_at,
        )


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    refresh_token: str

    @classmethod
    def from_pair(cls, pair: TokenPair) -> "TokenResponse":
        return cls(
            access_token=pair.access_token,
            expires_in=pair.expires_in,
            refresh_token=pair.refresh_token,
        )
