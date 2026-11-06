"""Graph API calls of the Embedded Signup flow.

Checked on 2026-11-06 against Meta's documentation, for Graph API v27.0.

Secrets travel in query strings where Meta documents them there, so nothing here may log a URL,
and an httpx exception, which holds the URL, must not leave this module.
"""

from typing import Any

import httpx
import structlog

from woassi.modules.shops.application.ports import MetaError, MetaFailure, MetaPhoneNumber
from woassi.shared.infrastructure.logging import silence_url_logging

log = structlog.get_logger()

GRAPH_URL = "https://graph.facebook.com"
INVALID_TOKEN_CODE = 190
CLOUD_API_PLATFORM = "CLOUD_API"


class HttpxMetaOnboarding:
    def __init__(
        self, client: httpx.AsyncClient, *, app_id: str, app_secret: str, graph_version: str
    ) -> None:
        silence_url_logging()
        self._client = client
        self._app_id = app_id
        self._app_secret = app_secret
        self._base_url = f"{GRAPH_URL}/{graph_version}"

    async def exchange_code(self, code: str) -> str:
        # https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-customers-as-a-solution-partner
        data = await self._request(
            "GET",
            "/oauth/access_token",
            params={
                "client_id": self._app_id,
                "client_secret": self._app_secret,
                "code": code,
            },
            invalid_request=MetaFailure.INVALID_CODE,
        )
        token = data.get("access_token")
        if not isinstance(token, str) or not token:
            raise MetaError(MetaFailure.REJECTED)
        return token

    async def subscribe_app(self, waba_id: str, token: str) -> None:
        # https://developers.facebook.com/documentation/business-messaging/whatsapp/solution-providers/manage-webhooks/
        await self._request("POST", f"/{waba_id}/subscribed_apps", token=token)

    async def get_phone_number(self, phone_number_id: str, token: str) -> MetaPhoneNumber:
        # https://developers.facebook.com/documentation/business-messaging/whatsapp/solution-providers/manage-phone-numbers
        # https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users/
        data = await self._request(
            "GET",
            f"/{phone_number_id}",
            params={"fields": "display_phone_number,verified_name,is_on_biz_app,platform_type"},
            token=token,
        )
        return MetaPhoneNumber(
            display_phone_number=str(data.get("display_phone_number", "")),
            verified_name=str(data.get("verified_name", "")),
            on_business_app=data.get("is_on_biz_app") is True,
            on_cloud_api=data.get("platform_type") == CLOUD_API_PLATFORM,
        )

    async def link_catalog(
        self, waba_id: str, phone_number_id: str, token: str, catalog_id: str | None
    ) -> str | None:
        # https://developers.facebook.com/docs/graph-api/reference/whatsapp-business-account/product_catalogs/
        data = await self._request("GET", f"/{waba_id}/product_catalogs", token=token)
        catalogs = data.get("data")
        linked = catalogs[0].get("id") if isinstance(catalogs, list) and catalogs else None
        if linked is None and catalog_id is not None:
            await self._request(
                "POST",
                f"/{waba_id}/product_catalogs",
                params={"catalog_id": catalog_id},
                token=token,
            )
            linked = catalog_id
        if linked is None:
            return None

        # https://developers.facebook.com/documentation/business-messaging/whatsapp/catalogs/set-commerce-settings
        await self._request(
            "POST",
            f"/{phone_number_id}/whatsapp_commerce_settings",
            params={"is_catalog_visible": "true", "is_cart_enabled": "true"},
            token=token,
        )
        return str(linked)

    async def sync_business_app_data(self, phone_number_id: str, token: str) -> None:
        # https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users/
        for sync_type in ("smb_app_state_sync", "history"):
            data = await self._request(
                "POST",
                f"/{phone_number_id}/smb_app_data",
                json={"messaging_product": "whatsapp", "sync_type": sync_type},
                token=token,
            )
            # Meta asks to keep this id for support.
            log.info(
                "whatsapp_sync_requested", sync_type=sync_type, request_id=data.get("request_id")
            )

    async def unsubscribe_app(self, waba_id: str, token: str) -> None:
        # https://developers.facebook.com/documentation/business-messaging/whatsapp/solution-providers/manage-webhooks/
        await self._request("DELETE", f"/{waba_id}/subscribed_apps", token=token)

    async def token_is_valid(self, token: str) -> bool:
        # https://developers.facebook.com/docs/graph-api/reference/debug_token/
        data = await self._request(
            "GET",
            "/debug_token",
            params={"input_token": token, "access_token": f"{self._app_id}|{self._app_secret}"},
        )
        details = data.get("data")
        return isinstance(details, dict) and details.get("is_valid") is True

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: dict[str, str] | None = None,
        token: str | None = None,
        invalid_request: MetaFailure = MetaFailure.REJECTED,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {token}"} if token else None
        try:
            response = await self._client.request(
                method, f"{self._base_url}{path}", params=params, json=json, headers=headers
            )
            data = response.json()
        except (httpx.HTTPError, ValueError):
            # `from None`: the original exception holds the URL, and so the secrets.
            raise MetaError(MetaFailure.UNAVAILABLE) from None

        if response.is_success and isinstance(data, dict):
            return data
        error = data.get("error", {}) if isinstance(data, dict) else {}
        meta_code = error.get("code") if isinstance(error, dict) else None
        if response.status_code >= 500:
            raise MetaError(MetaFailure.UNAVAILABLE, meta_code=meta_code)
        if meta_code == INVALID_TOKEN_CODE and invalid_request is MetaFailure.REJECTED:
            raise MetaError(MetaFailure.INVALID_TOKEN, meta_code=meta_code)
        raise MetaError(invalid_request, meta_code=meta_code)
