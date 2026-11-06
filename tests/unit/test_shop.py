from datetime import UTC, datetime
from uuid import uuid4

import pytest

from woassi.modules.shops.domain.errors import (
    InvalidReceivingAccount,
    InvalidSettings,
    InvalidShop,
    ShopNotActivatable,
    WhatsAppAlreadyConnected,
)
from woassi.modules.shops.domain.events import (
    ReceivingAccountChanged,
    ShopCreated,
    WhatsAppConnected,
)
from woassi.modules.shops.domain.shop import (
    Operator,
    ReceivingAccount,
    Shop,
    ShopSettings,
    ShopStatus,
    WhatsAppStatus,
    logo_key,
    slugify,
    with_random_suffix,
)
from woassi.shared.domain.values import PhoneNumber

NOW = datetime(2026, 1, 1, tzinfo=UTC)
PHONE = PhoneNumber("+22890123456")


def shop() -> Shop:
    return Shop.create(
        account_id=uuid4(),
        name=" Chez Ama ",
        slug="chez-ama",
        category="",
        city="",
        address="",
        now=NOW,
    )


def connect(target: Shop) -> None:
    target.connect_whatsapp(
        waba_id="1",
        phone_number_id="2",
        display_phone_number="+228 90 12 34 56",
        verified_name="Chez Ama",
        catalog_id=None,
        encrypted_token="encrypted",
        now=NOW,
    )


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Chez Ama", "chez-ama"),
        ("Épicerie du Marché", "epicerie-du-marche"),
        ("  --Boutique  N°1!  ", "boutique-n1"),
        ("!!!", "shop"),
        ("商店", "shop"),
    ],
)
def test_slugify(name: str, slug: str) -> None:
    assert slugify(name) == slug


def test_slug_stays_short() -> None:
    assert len(slugify("a" * 500)) <= 60


def test_random_suffix_differs() -> None:
    assert with_random_suffix("x") != with_random_suffix("x")


def test_create_starts_as_a_draft() -> None:
    created = shop()
    assert created.name == "Chez Ama"
    assert created.status is ShopStatus.DRAFT
    assert created.settings == ShopSettings()
    assert [type(event) for event in created.pull_events()] == [ShopCreated]


def test_name_is_required() -> None:
    with pytest.raises(InvalidShop):
        shop().rename(" ")


def test_renaming_keeps_the_slug() -> None:
    renamed = shop()
    renamed.rename("Autre nom")
    assert renamed.slug == "chez-ama"


def test_cannot_go_active_without_whatsapp() -> None:
    with pytest.raises(ShopNotActivatable):
        shop().activate()


def test_cannot_go_active_while_connecting() -> None:
    connecting = shop()
    connecting.start_whatsapp_connection("1")
    with pytest.raises(ShopNotActivatable):
        connecting.activate()


def test_connecting_activates_the_shop() -> None:
    connected = shop()
    connected.pull_events()
    connect(connected)
    assert connected.status is ShopStatus.ACTIVE
    assert [type(event) for event in connected.pull_events()] == [WhatsAppConnected]


def test_a_suspended_shop_stays_suspended() -> None:
    suspended = shop()
    suspended.status = ShopStatus.SUSPENDED
    connect(suspended)
    assert suspended.status is ShopStatus.SUSPENDED
    with pytest.raises(ShopNotActivatable):
        suspended.activate()


def test_cannot_start_over_a_connected_number() -> None:
    connected = shop()
    connect(connected)
    with pytest.raises(WhatsAppAlreadyConnected):
        connected.start_whatsapp_connection("1")


def test_a_failure_takes_the_shop_back_to_draft() -> None:
    failed = shop()
    connect(failed)
    failed.fail_whatsapp("Expired.")
    assert failed.whatsapp is not None
    assert failed.whatsapp.status is WhatsAppStatus.ERROR
    assert failed.whatsapp.error_message == "Expired."
    assert failed.status is ShopStatus.DRAFT


def test_a_suspended_shop_is_not_reactivated_by_a_failure() -> None:
    suspended = shop()
    connect(suspended)
    suspended.status = ShopStatus.SUSPENDED
    suspended.fail_whatsapp("Expired.")
    assert suspended.status is ShopStatus.SUSPENDED


def test_disconnecting_forgets_the_token_and_frees_the_number() -> None:
    disconnected = shop()
    connect(disconnected)
    disconnected.disconnect_whatsapp()
    assert disconnected.whatsapp is not None
    assert disconnected.whatsapp.status is WhatsAppStatus.DISCONNECTED
    assert disconnected.whatsapp.encrypted_token is None
    assert disconnected.whatsapp.phone_number_id is None
    assert disconnected.status is ShopStatus.DRAFT


def test_the_token_stays_out_of_repr() -> None:
    connected = shop()
    connect(connected)
    assert "encrypted'" not in repr(connected)


@pytest.mark.parametrize(
    "fields",
    [
        {"payment_modes": ()},
        {"reminder_1_minutes": 0},
        {"reminder_1_minutes": 60, "reminder_2_minutes": 60},
        {"reminder_2_minutes": 24 * 60},
        {"invoice_prefix": ""},
        {"invoice_prefix": "fac"},
        {"invoice_prefix": "TOO-LONG-PREFIX"},
    ],
)
def test_invalid_settings(fields: dict[str, object]) -> None:
    with pytest.raises(InvalidSettings):
        ShopSettings(**fields)  # type: ignore[arg-type]


def test_default_settings() -> None:
    settings = ShopSettings()
    assert (settings.reminder_1_minutes, settings.reminder_2_minutes) == (15, 60)
    assert settings.expiration_hours == 24
    assert settings.invoice_prefix == "FAC"


def test_receiving_account_needs_a_holder() -> None:
    with pytest.raises(InvalidReceivingAccount):
        ReceivingAccount(operator=Operator.MIXX, number=PHONE, holder_name=" ")


def test_changing_the_receiving_account_is_an_event() -> None:
    changed = shop()
    changed.pull_events()
    changed.set_receiving_account(None)
    assert [type(event) for event in changed.pull_events()] == [ReceivingAccountChanged]


def test_logo_key() -> None:
    shop_id, logo_id = uuid4(), uuid4()
    assert logo_key(shop_id, logo_id) == f"shops/{shop_id}/logo/{logo_id}.webp"
