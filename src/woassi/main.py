from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from woassi.config import Settings, get_settings
from woassi.container import Container
from woassi.modules.catalog.api.router import router as catalog_router
from woassi.modules.messaging.api.router import router as messaging_router
from woassi.shared.api.errors import register_error_handlers
from woassi.shared.infrastructure.logging import configure_logging, configure_sentry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    container = await Container.build(app.state.settings)
    app.state.container = container
    try:
        yield
    finally:
        await container.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.app_env)
    configure_sentry(settings.sentry_dsn, settings.app_env)

    app = FastAPI(title="Woassi API", lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(catalog_router)
    app.include_router(messaging_router)
    return app
