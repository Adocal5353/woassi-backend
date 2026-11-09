import pickle
from typing import Any

import pytest

from woassi.modules.messaging.application.extraction import extract_events
from woassi.modules.messaging.domain.event import (
    AccountUpdate,
    InboundMessage,
    MessageStatusUpdate,
)

PHONE_ID = "106540352242922"
BSUID = "TG.13491208655302741918"


def webhook(
    value: dict[str, Any], field: str = "messages", entry_id: str = "WABA_ID"
) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {"id": entry_id, "time": 1748477359, "changes": [{"value": value, "field": field}]}
        ],
    }


def messages(
    *items: dict[str, Any], contacts: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return webhook(
        {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "22890000000", "phone_number_id": PHONE_ID},
            "contacts": contacts
            if contacts is not None
            else [{"profile": {"name": "Ama"}, "wa_id": "22891234567", "user_id": BSUID}],
            "messages": list(items),
        }
    )


# The example of Meta's order reference, with Togolese values.
ORDER = {
    "from": "22891234567",
    "from_user_id": BSUID,
    "id": "wamid.ORDER",
    "timestamp": "1750096325",
    "type": "order",
    "order": {
        "catalog_id": "194836987003835",
        "text": "Livraison à Bè svp",
        "product_items": [
            {
                "product_retailer_id": "SKU-PAGNE",
                "quantity": 2,
                "item_price": 5000,
                "currency": "XOF",
            },
            {
                "product_retailer_id": "SKU-SAC",
                "quantity": 1,
                "item_price": 12500,
                "currency": "XOF",
            },
        ],
    },
}


def test_extracts_a_cart() -> None:
    [event] = extract_events(messages(ORDER))
    assert event == InboundMessage(
        phone_number_id=PHONE_ID,
        message_id="wamid.ORDER",
        type="order",
        sender_user_id=BSUID,
        sender_phone="22891234567",
        profile_name="Ama",
        payload=ORDER["order"],  # type: ignore[arg-type]
        timestamp=1750096325,
    )


def test_keeps_cart_lines() -> None:
    [event] = extract_events(messages(ORDER))
    assert isinstance(event, InboundMessage)
    assert event.payload["product_items"][0] == {
        "product_retailer_id": "SKU-PAGNE",
        "quantity": 2,
        "item_price": 5000,
        "currency": "XOF",
    }


def test_a_customer_with_a_username_has_no_phone_number() -> None:
    """Meta drops `from` and `wa_id` for users with a username; the BSUID is always there."""
    message = {k: v for k, v in ORDER.items() if k != "from"}
    contacts = [{"profile": {"name": "Ama", "username": "ama"}, "user_id": BSUID}]

    [event] = extract_events(messages(message, contacts=contacts))

    assert isinstance(event, InboundMessage)
    assert event.sender_phone is None
    assert event.sender_user_id == BSUID
    assert event.profile_name == "Ama"


def test_a_message_without_any_sender_is_skipped() -> None:
    message = {k: v for k, v in ORDER.items() if k not in ("from", "from_user_id")}
    assert extract_events(messages(message)) == []


def test_button_reply_keeps_the_message_it_answers() -> None:
    reply = {
        "from_user_id": BSUID,
        "id": "wamid.REPLY",
        "type": "interactive",
        "context": {"from": "22890000000", "id": "wamid.QUESTION"},
        "interactive": {
            "type": "button_reply",
            "button_reply": {"id": "accept:42", "title": "Valider"},
        },
    }
    [event] = extract_events(messages(reply))
    assert isinstance(event, InboundMessage)
    assert event.context_message_id == "wamid.QUESTION"
    assert event.payload["button_reply"]["id"] == "accept:42"


def test_profile_name_follows_the_sender() -> None:
    contacts = [
        {"profile": {"name": "Kofi"}, "user_id": "TG.1"},
        {"profile": {"name": "Ama"}, "user_id": BSUID},
    ]
    [event] = extract_events(messages(ORDER, contacts=contacts))
    assert isinstance(event, InboundMessage)
    assert event.profile_name == "Ama"


def test_message_types() -> None:
    items = [
        {"from_user_id": BSUID, "id": "a", "type": "text", "text": {"body": "Bonjour"}},
        {"from_user_id": BSUID, "id": "b", "type": "location", "location": {"latitude": 6.13}},
        {
            "from_user_id": BSUID,
            "id": "c",
            "type": "system",
            "system": {"type": "user_changed_number"},
        },
    ]
    events = extract_events(messages(*items))
    assert [e.type for e in events if isinstance(e, InboundMessage)] == [
        "text",
        "location",
        "system",
    ]


def test_statuses() -> None:
    value = {
        "metadata": {"phone_number_id": PHONE_ID},
        "statuses": [
            {"id": "wamid.1", "status": "delivered", "timestamp": "1", "recipient_user_id": BSUID},
            {
                "id": "wamid.2",
                "status": "failed",
                "timestamp": "1",
                "errors": [{"code": 131047, "title": "Re-engagement message"}],
            },
            {"status": "read"},
        ],
    }
    assert extract_events(webhook(value)) == [
        MessageStatusUpdate(phone_number_id=PHONE_ID, message_id="wamid.1", status="delivered"),
        MessageStatusUpdate(
            phone_number_id=PHONE_ID, message_id="wamid.2", status="failed", error_codes=(131047,)
        ),
    ]


def test_partner_removed_names_the_account_in_waba_info() -> None:
    value = {
        "event": "PARTNER_REMOVED",
        "waba_info": {"waba_id": "980198427658004", "owner_business_id": "1"},
    }
    assert extract_events(webhook(value, "account_update", entry_id="2949482758682047")) == [
        AccountUpdate(waba_id="980198427658004", event="PARTNER_REMOVED", time=1748477359)
    ]


def test_other_account_events_name_it_in_the_entry() -> None:
    [event] = extract_events(webhook({"event": "ACCOUNT_OFFBOARDED"}, "account_update", "102290"))
    assert event == AccountUpdate(waba_id="102290", event="ACCOUNT_OFFBOARDED", time=1748477359)


@pytest.mark.parametrize(
    "field", ["history", "smb_message_echoes", "smb_app_state_sync", "security"]
)
def test_other_fields_are_ignored(field: str) -> None:
    payload = messages(ORDER)
    payload["entry"][0]["changes"][0]["field"] = field
    assert extract_events(payload) == []


def test_routes_each_change_to_its_number() -> None:
    a = messages({"from_user_id": BSUID, "id": "a", "type": "text", "text": {"body": "x"}})
    b = messages({"from_user_id": BSUID, "id": "b", "type": "text", "text": {"body": "y"}})
    b["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"] = "222"
    a["entry"] += b["entry"]
    assert [e.phone_number_id for e in extract_events(a) if isinstance(e, InboundMessage)] == [
        PHONE_ID,
        "222",
    ]


def test_skips_malformed_items_without_losing_the_others() -> None:
    valid = {"from_user_id": BSUID, "id": "a", "type": "text", "text": {"body": "x"}}
    payload = messages("not an object", {"id": "no-sender"}, valid)  # type: ignore[arg-type]
    assert [e.message_id for e in extract_events(payload) if isinstance(e, InboundMessage)] == ["a"]


def test_unexpected_payloads() -> None:
    assert extract_events({}) == []
    assert extract_events({"entry": "x"}) == []
    assert extract_events({"entry": [{"changes": [{"value": {}, "field": "messages"}]}]}) == []
    assert extract_events(webhook({"event": ""}, "account_update")) == []


def test_personal_data_stays_out_of_repr() -> None:
    # arq logs the repr of every job's arguments.
    [event] = extract_events(messages(ORDER))
    shown = repr(event)
    for secret in ("22891234567", BSUID, "Ama", "Livraison"):
        assert secret not in shown
    assert "wamid.ORDER" in shown


@pytest.mark.parametrize(
    "event",
    [
        InboundMessage(phone_number_id="1", message_id="m", type="text", sender_user_id=BSUID),
        MessageStatusUpdate(phone_number_id="1", message_id="m", status="read"),
        AccountUpdate(waba_id="1", event="PARTNER_REMOVED"),
    ],
)
def test_events_survive_arq_serialization(event: object) -> None:
    assert pickle.loads(pickle.dumps(event)) == event
