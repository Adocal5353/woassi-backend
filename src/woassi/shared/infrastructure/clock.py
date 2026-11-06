from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

DISPLAY_TIMEZONE = ZoneInfo("Africa/Lome")


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def local_now(self) -> datetime:
        return self.now().astimezone(DISPLAY_TIMEZONE)


class FrozenClock:
    """For tests: time only moves when `advance` is called."""

    def __init__(self, current: datetime) -> None:
        self._current = current

    def now(self) -> datetime:
        return self._current

    def local_now(self) -> datetime:
        return self._current.astimezone(DISPLAY_TIMEZONE)

    def advance(self, delta: timedelta) -> None:
        self._current += delta
