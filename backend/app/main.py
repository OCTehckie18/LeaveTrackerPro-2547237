from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.api.middleware import (
    BodyLimitMiddleware,
    OriginCheckMiddleware,
    RequestContextMiddleware,
)
from app.api.routes import audit, auth, health, leaves
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db import get_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        get_engine().dispose()

    local = settings.app_env == "local"
    app = FastAPI(
        title="LeaveTrackerPro API",
        version=settings.app_version,
        lifespan=lifespan,
        # Interactive docs only on a developer machine (recon aid otherwise).
        docs_url="/api/docs" if local else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if local else None,
    )
    # Last added = outermost: request context wraps everything, then size limit, then Origin check.
    app.add_middleware(OriginCheckMiddleware, allowed_origins=settings.origins)
    max_body = (settings.max_upload_files * settings.max_upload_mb + 1) * 1024 * 1024
    app.add_middleware(BodyLimitMiddleware, max_bytes=max_body)
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(leaves.router)
    app.include_router(audit.router)
    return app


app = create_app()
