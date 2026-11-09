from types import SimpleNamespace
from typing import Any

import pytest
from arq import Retry

from woassi.modules.messaging.domain.event import InboundMessage


@pytest.fixture
def worker(monkeypatch: pytest.MonkeyPatch) -> Any:
    for name, value in {
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/test",
        "REDIS_URL": "redis://localhost:6379/0",
        "MINIO_ENDPOINT": "localhost:9000",
        "MINIO_PUBLIC_ENDPOINT": "localhost:9000",
        "MINIO_ACCESS_KEY": "key",
        "MINIO_SECRET_KEY": "secret",
        "PUBLIC_IMAGES_BASE_URL": "http://x",
        "META_APP_ID": "app",
        "META_APP_SECRET": "secret",
        "META_VERIFY_TOKEN": "token",
        "JWT_SECRET": "x" * 40,
        "WOASSI_ENCRYPTION_KEY": "key",
    }.items():
        monkeypatch.setenv(name, value)
    from woassi import worker

    return worker


def context(job_try: int, failing: bool) -> dict[str, Any]:
    class Handle:
        async def execute(self, event: object) -> None:
            if failing:
                raise ConnectionError("database down")

    return {"job_try": job_try, "container": SimpleNamespace(handle_meta_event=Handle)}


EVENT = InboundMessage(phone_number_id="1", message_id="m", type="text", sender_user_id="TG.1")


async def test_a_failure_is_retried_later(worker: Any) -> None:
    with pytest.raises(Retry) as caught:
        await worker.process_meta_event(context(1, failing=True), EVENT)
    assert caught.value.defer_score == worker.RETRY_DELAY_S * 1000


async def test_the_last_try_gives_up_loudly(worker: Any) -> None:
    with pytest.raises(ConnectionError):
        await worker.process_meta_event(context(worker.MAX_TRIES, failing=True), EVENT)


async def test_success(worker: Any) -> None:
    await worker.process_meta_event(context(1, failing=False), EVENT)


def test_worker_allows_the_retries(worker: Any) -> None:
    assert worker.WorkerSettings.max_tries == worker.MAX_TRIES
    assert worker.process_meta_event in worker.WorkerSettings.functions
