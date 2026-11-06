from typing import Any
from uuid import UUID

import structlog
from arq.connections import RedisSettings

from woassi.config import get_settings
from woassi.container import Container
from woassi.modules.messaging.domain.event import MetaEvent
from woassi.shared.domain.events import DomainEvent
from woassi.shared.infrastructure.logging import configure_logging, configure_sentry

log = structlog.get_logger()


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
    # TODO: idempotency with process_once on message_id, then routing to orders.
    log.info(
        "meta_event_received",
        phone_number_id=event.phone_number_id,
        message_id=event.message_id,
        type=event.type,
    )


async def dispatch_event(ctx: dict[str, Any], subscriber: str, event: DomainEvent) -> None:
    await ctx["container"].event_bus.dispatch(subscriber, event)


class WorkerSettings:
    functions = (process_photo, process_meta_event, dispatch_event)
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    # With no stored result, the process_photo job id is freed as soon as the job ends.
    keep_result = 0
