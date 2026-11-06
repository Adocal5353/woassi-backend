import logging

import sentry_sdk
import structlog


def configure_logging(app_env: str) -> None:
    """Structlog: console output in dev, JSON in other environments."""
    renderer: structlog.typing.Processor = (
        structlog.dev.ConsoleRenderer() if app_env == "dev" else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


def configure_sentry(dsn: str | None, app_env: str) -> None:
    if dsn:
        sentry_sdk.init(dsn=dsn, environment=app_env)
