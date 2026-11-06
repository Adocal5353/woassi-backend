import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

import structlog

log = structlog.get_logger()

type ReadinessCheck = Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    checks: dict[str, bool]

    @property
    def ready(self) -> bool:
        return all(self.checks.values())


class CheckReadiness:
    def __init__(self, checks: Mapping[str, ReadinessCheck], *, timeout_s: float = 2.0) -> None:
        self._checks = checks
        self._timeout_s = timeout_s

    async def execute(self) -> ReadinessReport:
        results = await asyncio.gather(*(self._run(name) for name in self._checks))
        return ReadinessReport(checks=dict(zip(self._checks, results, strict=True)))

    async def _run(self, name: str) -> bool:
        try:
            async with asyncio.timeout(self._timeout_s):
                await self._checks[name]()
        except Exception as error:
            log.warning("readiness_check_failed", check=name, error=type(error).__name__)
            return False
        return True
