from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PageResult[T]:
    items: list[T]
    total: int
    offset: int
    limit: int
