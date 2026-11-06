import asyncio

from woassi.shared.application.readiness import CheckReadiness


async def ok() -> None:
    return None


async def failing() -> None:
    raise ConnectionError


async def hanging() -> None:
    await asyncio.sleep(60)


async def test_ready_when_every_check_passes() -> None:
    report = await CheckReadiness({"a": ok, "b": ok}).execute()
    assert report.ready
    assert report.checks == {"a": True, "b": True}


async def test_a_failure_is_reported_by_name() -> None:
    report = await CheckReadiness({"a": ok, "b": failing}).execute()
    assert not report.ready
    assert report.checks == {"a": True, "b": False}


async def test_a_hanging_dependency_times_out() -> None:
    report = await CheckReadiness({"a": hanging}, timeout_s=0.01).execute()
    assert report.checks == {"a": False}
