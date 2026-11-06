import pytest

from woassi.shared.domain.errors import InvalidData
from woassi.shared.domain.values import PhoneNumber
from woassi.shared.infrastructure.phone import PhonenumbersNormalizer


@pytest.mark.parametrize("value", ["+22890123456", "+33612345678"])
def test_accepts_e164(value: str) -> None:
    assert str(PhoneNumber(value)) == value


@pytest.mark.parametrize("value", ["22890123456", "+0123456789", "+228 90 12 34 56", "+12", ""])
def test_rejects_anything_else(value: str) -> None:
    with pytest.raises(InvalidData):
        PhoneNumber(value)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("90 12 34 56", "+22890123456"),
        ("90123456", "+22890123456"),
        ("+228 90 12 34 56", "+22890123456"),
        ("00228 90 12 34 56", "+22890123456"),
        ("+33 6 12 34 56 78", "+33612345678"),
    ],
)
def test_normalizes_to_e164_with_togo_as_default(raw: str, expected: str) -> None:
    assert PhonenumbersNormalizer().normalize(raw) == PhoneNumber(expected)


def test_normalizes_a_whatsapp_sender_without_plus() -> None:
    assert PhonenumbersNormalizer().normalize("22890123456").value == "+22890123456"


@pytest.mark.parametrize("raw", ["", "abc", "123", "+228 00 00"])
def test_rejects_invalid_numbers(raw: str) -> None:
    with pytest.raises(InvalidData) as error:
        PhonenumbersNormalizer().normalize(raw)
    assert error.value.code == "phone.invalid"
