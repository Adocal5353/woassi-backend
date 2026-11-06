from dataclasses import dataclass

from woassi.shared.domain.errors import InvalidData


@dataclass(frozen=True, slots=True, order=True)
class Amount:
    """Amount in CFA francs (XOF): a non-negative integer, no cents."""

    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise InvalidData("An amount must be an integer.", code="amount.invalid")
        if self.value < 0:
            raise InvalidData("An amount cannot be negative.", code="amount.negative")

    def __add__(self, other: "Amount") -> "Amount":
        return Amount(self.value + other.value)

    def __mul__(self, quantity: int) -> "Amount":
        return Amount(self.value * quantity)

    def __str__(self) -> str:
        return f"{self.value:,} FCFA".replace(",", " ")
