from __future__ import annotations

from typing import cast

from fastapi import Request
from psycopg_pool import AsyncConnectionPool

from .config import Settings
from .logging import JsonLogger


def pool_of(request: Request) -> AsyncConnectionPool:
    return cast(AsyncConnectionPool, request.app.state.pool)


def settings_of(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def logger_of(request: Request) -> JsonLogger:
    return cast(JsonLogger, request.app.state.logger)
