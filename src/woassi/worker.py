from typing import Any
from uuid import UUID

import structlog
from arq import Retry, cron
from arq.connections import RedisSettings

from woassi.config import get_settings
from woassi.container import Container
from woassi.modules.messaging.domain.event import MetaEvent
from woassi.shared.domain.events import DomainEvent
from woassi.shared.infrastructure.logging import configure_logging, configure_sentry

log = structlog.get_logger()

MAX_TRIES = 5
RETRY_DELAY_S = 30


async def on_startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.app_env)
    configure_sentry(settings.sentry_dsn, settings.app_env)
    ctx["container"] = await Container.build(settings)


async def on_shutdown(ctx: dict[str, Any]) -> None:
    await ctx["container"].close()


async def process_photo(ctx: dict[str, Any], photo_id: str) -> None:
    await ctx["container"].process_photo().execute(UUID(photo_id))


async def process_meta_event(ctx: dict[str, Any], event: MetaEvent) -> None:
    """Meta does not resend once the API answered 200: the worker has to retry by itself."""
    try:
        await ctx["container"].handle_meta_event().execute(event)
    except Exception as error:
        if ctx["job_try"] >= MAX_TRIES:
            log.exception("meta_event_dropped", job_try=ctx["job_try"], meta_event=repr(event))
            raise
        raise Retry(defer=RETRY_DELAY_S * ctx["job_try"]) from error


async def dispatch_event(ctx: dict[str, Any], subscriber: str, event: DomainEvent) -> None:
    await ctx["container"].event_bus.dispatch(subscriber, event)


async def check_whatsapp_tokens(ctx: dict[str, Any]) -> None:
    invalid = await ctx["container"].check_whatsapp_tokens().execute()
    log.info("whatsapp_tokens_checked", invalid=invalid)


class WorkerSettings:
    functions = (process_photo, process_meta_event, dispatch_event)
    cron_jobs = (cron(check_whatsapp_tokens, hour=3, minute=0, timeout=3600),)
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    # With no stored result, the process_photo job id is freed as soon as the job ends.
    keep_result = 0
    max_tries = MAX_TRIES
