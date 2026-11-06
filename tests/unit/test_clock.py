from datetime import UTC, datetime, timedelta

from woassi.shared.infrastructure.clock import FrozenClock, SystemClock


def test_system_clock_is_utc() -> None:
    assert SystemClock().now().utcoffset() == timedelta(0)


def test_system_clock_displays_lome_time() -> None:
    assert str(SystemClock().local_now().tzinfo) == "Africa/Lome"


def test_frozen_clock_only_moves_when_told() -> None:
    start = datetime(2026, 1, 1, 12, tzinfo=UTC)
    clock = FrozenClock(start)
    assert clock.now() == start

    clock.advance(timedelta(minutes=15))

    assert clock.now() == start + timedelta(minutes=15)
    assert clock.local_now() == clock.now()
    assert str(clock.local_now().tzinfo) == "Africa/Lome"
