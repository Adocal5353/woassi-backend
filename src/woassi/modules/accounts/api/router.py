from typing import Annotated

from fastapi import APIRouter, Cookie, Request, Response, status

from woassi.modules.accounts.api.deps import AccountsDep
from woassi.modules.accounts.api.schemas import (
    AccountResponse,
    AccountUpdate,
    LoginRequest,
    PasswordChange,
    PasswordReset,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    VerifyPhoneRequest,
)
from woassi.modules.accounts.application.dto import TokenPair
from woassi.modules.accounts.domain.errors import InvalidRefreshToken
from woassi.shared.api.deps import CurrentAccount, client_ip

COOKIE_NAME = "refresh_token"
COOKIE_PATH = "/auth"

auth_router = APIRouter(prefix="/auth", tags=["auth"])
me_router = APIRouter(prefix="/me", tags=["account"])

RefreshCookie = Annotated[str | None, Cookie(alias=COOKIE_NAME)]


def _set_refresh_cookie(response: Response, pair: TokenPair) -> None:
    response.set_cookie(
        COOKIE_NAME,
        pair.refresh_token,
        max_age=pair.refresh_expires_in,
        path=COOKIE_PATH,
        httponly=True,
        secure=True,
        samesite="lax",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        COOKIE_NAME, path=COOKIE_PATH, httponly=True, secure=True, samesite="lax"
    )


@auth_router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, accounts: AccountsDep) -> AccountResponse:
    account = await accounts.register().execute(**body.model_dump())
    return AccountResponse.from_view(account)


@auth_router.post("/verify", status_code=status.HTTP_204_NO_CONTENT)
async def verify_phone(body: VerifyPhoneRequest, accounts: AccountsDep) -> None:
    await accounts.verify_phone().execute(phone=body.phone, code=body.code)


@auth_router.post("/login")
async def login(
    body: LoginRequest, request: Request, response: Response, accounts: AccountsDep
) -> TokenResponse:
    pair = await accounts.login().execute(
        phone=body.phone, password=body.password, ip=client_ip(request)
    )
    _set_refresh_cookie(response, pair)
    return TokenResponse.from_pair(pair)


@auth_router.post("/refresh")
async def refresh(
    response: Response,
    accounts: AccountsDep,
    cookie: RefreshCookie = None,
    body: RefreshRequest | None = None,
) -> TokenResponse:
    token = (body.refresh_token if body else None) or cookie
    if token is None:
        raise InvalidRefreshToken("Invalid refresh token.")
    pair = await accounts.refresh_tokens().execute(token)
    _set_refresh_cookie(response, pair)
    return TokenResponse.from_pair(pair)


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    accounts: AccountsDep,
    cookie: RefreshCookie = None,
    body: RefreshRequest | None = None,
) -> None:
    token = (body.refresh_token if body else None) or cookie
    if token is not None:
        await accounts.logout().execute(token)
    _clear_refresh_cookie(response)


@auth_router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(response: Response, account: CurrentAccount, accounts: AccountsDep) -> None:
    await accounts.logout_everywhere().execute(account.id)
    _clear_refresh_cookie(response)


@auth_router.post("/password/request", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(body: PasswordResetRequest, accounts: AccountsDep) -> None:
    await accounts.request_password_reset().execute(body.phone)


@auth_router.post("/password/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(body: PasswordReset, accounts: AccountsDep) -> None:
    await accounts.reset_password().execute(
        phone=body.phone, code=body.code, new_password=body.new_password
    )


@me_router.get("")
async def get_me(account: CurrentAccount, accounts: AccountsDep) -> AccountResponse:
    return AccountResponse.from_view(await accounts.get_my_account().execute(account.id))


@me_router.patch("")
async def update_me(
    body: AccountUpdate, account: CurrentAccount, accounts: AccountsDep
) -> AccountResponse:
    updated = await accounts.update_my_account().execute(
        account_id=account.id, **body.model_dump(exclude_unset=True)
    )
    return AccountResponse.from_view(updated)


@me_router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: PasswordChange, response: Response, account: CurrentAccount, accounts: AccountsDep
) -> None:
    await accounts.change_password().execute(
        account_id=account.id,
        current_password=body.current_password,
        new_password=body.new_password,
    )
    _clear_refresh_cookie(response)
