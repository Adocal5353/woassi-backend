from datetime import UTC, datetime
from typing import Any, cast

import pytest

from woassi.shared.domain.events import DomainEvent, Entity
from woassi.shared.infrastructure.clock import FrozenClock
from woassi.shared.infrastructure.db.uow import SqlAlchemyUnitOfWork


class StubSession:
    """Only records calls: event timing does not depend on a real database."""

    def __init__(self, journal: list[str], *, failing_commit: bool = False) -> None:
        self.journal = journal
        self.failing_commit = failing_commit

    async def commit(self) -> None:
        if self.failing_commit:
            raise ConnectionError
        self.journal.append("commit")

    async def rollback(self) -> None:
        self.journal.append("rollback")

    async def close(self) -> None:
        self.journal.append("close")


class StubBus:
    def __init__(self, journal: list[str]) -> None:
        self.journal = journal

    async def publish(self, event: DomainEvent) -> None:
        self.journal.append("publish")


def unit_of_work(journal: list[str], *, failing_commit: bool = False) -> SqlAlchemyUnitOfWork:
    def sessions() -> Any:
        return StubSession(journal, failing_commit=failing_commit)

    clock = FrozenClock(datetime(2026, 1, 1, tzinfo=UTC))
    return SqlAlchemyUnitOfWork(cast(Any, sessions), StubBus(journal), clock)


def entity_with_event() -> Entity:
    entity = Entity()
    entity.record_event(DomainEvent())
    return entity


async def test_events_are_published_after_the_commit() -> None:
    journal: list[str] = []
    async with unit_of_work(journal) as uow:
        uow._track(entity_with_event())
        await uow.commit()
    assert journal[:2] == ["commit", "publish"]


async def test_nothing_is_published_on_rollback() -> None:
    journal: list[str] = []
    async with unit_of_work(journal) as uow:
        uow._track(entity_with_event())
        await uow.rollback()
        await uow.commit()
    assert "publish" not in journal


async def test_nothing_is_published_when_the_block_exits_without_commit() -> None:
    journal: list[str] = []
    async with unit_of_work(journal) as uow:
        uow._track(entity_with_event())
    assert "publish" not in journal


async def test_nothing_is_published_when_the_block_raises() -> None:
    journal: list[str] = []
    with pytest.raises(ValueError):
        async with unit_of_work(journal) as uow:
            uow._track(entity_with_event())
            raise ValueError
    assert "publish" not in journal


async def test_nothing_is_published_when_the_commit_fails() -> None:
    journal: list[str] = []
    with pytest.raises(ConnectionError):
        async with unit_of_work(journal, failing_commit=True) as uow:
            uow._track(entity_with_event())
            await uow.commit()
    assert "publish" not in journal


async def test_an_event_is_published_only_once() -> None:
    journal: list[str] = []
    async with unit_of_work(journal) as uow:
        entity = entity_with_event()
        uow._track(entity)
        uow._track(entity)
        await uow.commit()
        await uow.commit()
    assert journal.count("publish") == 1
