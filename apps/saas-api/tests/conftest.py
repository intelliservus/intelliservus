from __future__ import annotations

import io
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from psycopg_pool import AsyncConnectionPool

from saas_api.app import create_app
from saas_api.common.config import Settings
from saas_api.modules.auth.password import hash_password
from support import DSN, PASSWORD, Call, truncate

ORIGIN = "http://localhost:8080"


def _make_call(app: FastAPI, *, raise_app_exceptions: bool = True) -> Call:
    async def _call(
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        json: Any = None,
        content: bytes | None = None,
    ) -> Response:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions),
            base_url="http://test",
        ) as client:
            return await client.request(method, path, headers=headers, json=json, content=content)

    return _call


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="test",
        database_url=DSN or "postgres://user:pass@localhost:5432/platform",
        jwt_secret="a" * 32,
        allowed_origins=[ORIGIN],
        cookie_secure=False,
        webhook_secrets=["test-webhook-secret"],
    )


@pytest.fixture
def log_stream() -> io.StringIO:
    return io.StringIO()


@pytest.fixture
def app(settings: Settings, log_stream: io.StringIO) -> FastAPI:
    return create_app(settings, log_stream=log_stream)


@pytest_asyncio.fixture
async def call(app: FastAPI) -> Call:
    return _make_call(app)


@pytest.fixture(scope="session")
def password_hash() -> str:
    return hash_password(PASSWORD)


@pytest_asyncio.fixture
async def admin_pool() -> AsyncIterator[AsyncConnectionPool]:
    if not DSN:
        pytest.skip("TEST_DATABASE_URL not set")
    pool = AsyncConnectionPool(
        DSN,
        kwargs={"options": "-c app.scope=platform"},
        open=False,
        min_size=1,
        max_size=4,
    )
    await pool.open()
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def raw_pool() -> AsyncIterator[AsyncConnectionPool]:
    if not DSN:
        pytest.skip("TEST_DATABASE_URL not set")
    pool = AsyncConnectionPool(
        DSN,
        kwargs={"options": "-c role=saas_app"},
        open=False,
        min_size=1,
        max_size=10,
    )
    await pool.open()
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def ingress_pool() -> AsyncIterator[AsyncConnectionPool]:
    if not DSN:
        pytest.skip("TEST_DATABASE_URL not set")
    pool = AsyncConnectionPool(
        DSN,
        kwargs={"options": "-c role=saas_ingress"},
        open=False,
        min_size=1,
        max_size=4,
    )
    await pool.open()
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def app_pool() -> AsyncIterator[AsyncConnectionPool]:
    if not DSN:
        pytest.skip("TEST_DATABASE_URL not set")
    pool = AsyncConnectionPool(DSN, open=False, min_size=1, max_size=10)
    await pool.open()
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def clean_db(admin_pool: AsyncConnectionPool) -> AsyncIterator[None]:
    await truncate(admin_pool)
    yield
    await truncate(admin_pool)


@pytest_asyncio.fixture
async def db_app(
    settings: Settings,
    app_pool: AsyncConnectionPool,
    log_stream: io.StringIO,
) -> FastAPI:
    return create_app(settings, pool=app_pool, log_stream=log_stream)


@pytest_asyncio.fixture
async def db_call(db_app: FastAPI) -> Call:
    return _make_call(db_app)
