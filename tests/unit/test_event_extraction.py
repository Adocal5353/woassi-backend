import pickle
from typing import Any

from woassi.modules.messaging.application.extraction import extract_events
from woassi.modules.messaging.domain.event import MetaEvent


def payload(phone_number_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "22890000000",
                                "phone_number_id": phone_number_id,
                            },
                            "contacts": [{"profile": {"name": "Ama"}, "wa_id": "22891234567"}],
                            "messages": messages,
                        },
                    }
                ],
            }
        ],
    }


ORDER = {
    "from": "22891234567",
    "id": "wamid.ORDER",
    "timestamp": "1760000000",
    "type": "order",
    "order": {
        "catalog_id": "CATALOG_ID",
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
    assert extract_events(payload("111", [ORDER])) == [
        MetaEvent(
            phone_number_id="111",
            message_id="wamid.ORDER",
            sender="22891234567",
            type="order",
            payload=ORDER["order"],  # type: ignore[arg-type]
        )
    ]


def test_keeps_cart_lines() -> None:
    [event] = extract_events(payload("111", [ORDER]))
    assert event.payload["product_items"][0] == {
        "product_retailer_id": "SKU-PAGNE",
        "quantity": 2,
        "item_price": 5000,
        "currency": "XOF",
    }


def test_message_types() -> None:
    messages = [
        {"from": "1", "id": "a", "type": "text", "text": {"body": "Bonjour"}},
        {
            "from": "1",
            "id": "b",
            "type": "interactive",
            "interactive": {"type": "button_reply", "button_reply": {"id": "valider"}},
        },
        {"from": "1", "id": "c", "type": "location", "location": {"latitude": 6.13}},
    ]
    events = extract_events(payload("111", messages))
    assert [e.type for e in events] == ["text", "interactive", "location"]
    assert events[0].payload == {"body": "Bonjour"}


def test_routes_each_change_to_its_number() -> None:
    a = payload("111", [{"from": "1", "id": "a", "type": "text", "text": {"body": "x"}}])
    b = payload("222", [{"from": "1", "id": "b", "type": "text", "text": {"body": "y"}}])
    a["entry"] += b["entry"]
    assert [e.phone_number_id for e in extract_events(a)] == ["111", "222"]


def test_status_notification_without_message() -> None:
    body = payload("111", [])
    del body["entry"][0]["changes"][0]["value"]["messages"]
    body["entry"][0]["changes"][0]["value"]["statuses"] = [{"id": "x", "status": "delivered"}]
    assert extract_events(body) == []


def test_skips_malformed_items_without_losing_the_others() -> None:
    valid = {"from": "1", "id": "a", "type": "text", "text": {"body": "x"}}
    body = payload("111", ["not an object", {"id": "no-sender"}, valid])  # type: ignore[list-item]
    assert [e.message_id for e in extract_events(body)] == ["a"]


def test_unexpected_payloads() -> None:
    assert extract_events({}) == []
    assert extract_events({"entry": "x"}) == []
    assert extract_events({"entry": [{"changes": [{"value": {}}]}]}) == []


def test_personal_data_stays_out_of_repr() -> None:
    # arq logs the repr of every job's arguments.
    [event] = extract_events(payload("111", [ORDER]))
    assert "22891234567" not in repr(event)
    assert "Livraison" not in repr(event)
    assert "wamid.ORDER" in repr(event)


def test_event_survives_arq_serialization() -> None:
    [event] = extract_events(payload("111", [ORDER]))
    assert pickle.loads(pickle.dumps(event)) == event
