import pytest

from woassi.shared.domain.errors import InvalidData
from woassi.shared.domain.values import Amount


def test_adds_and_multiplies() -> None:
    assert Amount(1500) + Amount(500) == Amount(2000)
    assert Amount(1500) * 3 == Amount(4500)


def test_displays_in_fcfa() -> None:
    assert str(Amount(1250000)) == "1 250 000 FCFA"


@pytest.mark.parametrize("value", [-1, 10.5, True, "100"])
def test_rejects_invalid_values(value: object) -> None:
    with pytest.raises(InvalidData):
        Amount(value)  # type: ignore[arg-type]
