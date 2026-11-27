from __future__ import annotations

from psycopg_pool import AsyncConnectionPool


def create_pool(dsn: str, *, min_size: int = 1, max_size: int = 10) -> AsyncConnectionPool:
    return AsyncConnectionPool(dsn, open=False, min_size=min_size, max_size=max_size)
