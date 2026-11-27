from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TextIO

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg_pool import AsyncConnectionPool
from starlette.exceptions import HTTPException as StarletteHTTPException

from .common.config import SERVICE_NAME, Settings
from .common.envelope import error_body
from .common.errors import STATUS_CODES, AppError
from .common.logging import JsonLogger
from .common.middleware import RequestContextMiddleware
from .database.pool import create_pool
from .modules.auth.router import router as auth_router
from .modules.health.router import router as health_router
from .modules.ingress.router import router as ingress_router
from .modules.tenant.router import router as tenant_router


def create_app(
    settings: Settings,
    *,
    pool: AsyncConnectionPool | None = None,
    log_stream: TextIO | None = None,
) -> FastAPI:
    logger = JsonLogger(SERVICE_NAME, log_stream)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if pool is None:
            application.state.pool = create_pool(settings.database_url)
            await application.state.pool.open()
        else:
            application.state.pool = pool
        try:
            yield
        finally:
            if pool is None:
                await application.state.pool.close()

    application = FastAPI(lifespan=lifespan)
    application.state.settings = settings
    application.state.logger = logger
    if pool is not None:
        application.state.pool = pool
    application.add_middleware(RequestContextMiddleware, logger=logger)
    application.include_router(health_router, prefix="/api/v1")
    application.include_router(auth_router, prefix="/api/v1")
    application.include_router(ingress_router, prefix="/api/v1")
    application.include_router(tenant_router, prefix="/api/v1")

    @application.exception_handler(AppError)
    async def _handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content=error_body(exc.code, exc.message, exc.details),
        )

    @application.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        violations = [
            f"{'.'.join(str(part) for part in error['loc'][1:]) or '(root)'}: {error['msg']}"
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=400,
            content=error_body("PARAM_INVALID", "; ".join(violations), {"violations": violations}),
        )

    @application.exception_handler(StarletteHTTPException)
    async def _handle_http_error(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = STATUS_CODES.get(exc.status_code, "SYS_INTERNAL")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return JSONResponse(status_code=exc.status_code, content=error_body(code, message))

    return application
