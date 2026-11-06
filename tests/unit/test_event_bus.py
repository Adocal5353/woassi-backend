from dataclasses import dataclass, field

import pytest

from woassi.shared.domain.events import DomainEvent
from woassi.shared.infrastructure.events.bus import InProcessEventBus


@dataclass(frozen=True, kw_only=True)
class SomethingHappened(DomainEvent):
    what: str = "x"


@dataclass(frozen=True, kw_only=True)
class SomethingElseHappened(DomainEvent):
    pass


@dataclass
class FakeDispatcher:
    deferred: list[tuple[str, DomainEvent]] = field(default_factory=list)

    async def defer(self, subscriber: str, event: DomainEvent) -> None:
        self.deferred.append((subscriber, event))


class Recorder:
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    async def __call__(self, event: DomainEvent) -> None:
        self.events.append(event)


def test_events_get_an_id_and_a_utc_timestamp() -> None:
    first, second = SomethingHappened(), SomethingHappened()
    assert first.event_id != second.event_id
    assert first.occurred_at.utcoffset() is not None


async def test_publish_reaches_subscribers_of_that_event_only() -> None:
    bus, recorder = InProcessEventBus(), Recorder()
    bus.subscribe(SomethingHappened, recorder, name="recorder")

    event = SomethingHappened()
    await bus.publish(event)
    await bus.publish(SomethingElseHappened())

    assert recorder.events == [event]


async def test_a_failing_subscriber_does_not_stop_the_others_or_the_caller() -> None:
    async def failing(_: DomainEvent) -> None:
        raise RuntimeError("boom")

    bus, recorder = InProcessEventBus(), Recorder()
    bus.subscribe(SomethingHappened, failing, name="failing")
    bus.subscribe(SomethingHappened, recorder, name="recorder")

    await bus.publish(SomethingHappened())

    assert len(recorder.events) == 1


async def test_deferred_subscriber_goes_through_the_dispatcher() -> None:
    dispatcher, recorder = FakeDispatcher(), Recorder()
    bus = InProcessEventBus(dispatcher)
    bus.subscribe(SomethingHappened, recorder, name="later", deferred=True)

    event = SomethingHappened()
    await bus.publish(event)

    assert recorder.events == []
    assert dispatcher.deferred == [("later", event)]

    await bus.dispatch("later", event)
    assert recorder.events == [event]


async def test_a_failing_dispatcher_does_not_reach_the_caller() -> None:
    class BrokenDispatcher:
        async def defer(self, subscriber: str, event: DomainEvent) -> None:
            raise ConnectionError

    bus = InProcessEventBus(BrokenDispatcher())
    bus.subscribe(SomethingHappened, Recorder(), name="later", deferred=True)

    await bus.publish(SomethingHappened())


async def test_dispatch_propagates_errors_to_the_worker() -> None:
    async def failing(_: DomainEvent) -> None:
        raise RuntimeError("boom")

    bus = InProcessEventBus(FakeDispatcher())
    bus.subscribe(SomethingHappened, failing, name="later", deferred=True)

    with pytest.raises(RuntimeError):
        await bus.dispatch("later", SomethingHappened())


def test_subscriber_names_are_unique() -> None:
    bus = InProcessEventBus()
    bus.subscribe(SomethingHappened, Recorder(), name="same")
    with pytest.raises(ValueError):
        bus.subscribe(SomethingElseHappened, Recorder(), name="same")


def test_deferred_subscriber_needs_a_dispatcher() -> None:
    with pytest.raises(ValueError):
        InProcessEventBus().subscribe(SomethingHappened, Recorder(), name="x", deferred=True)
