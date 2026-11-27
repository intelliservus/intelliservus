from __future__ import annotations

from typing import Any

import pytest

from saas_api.database.repository import Repository
from saas_api.database.transaction import tenant_context


class FakeTransaction:
    def __init__(self, queries: list[tuple[str, Any]]) -> None:
        self.queries = queries

    async def __aenter__(self) -> FakeTransaction:
        self.queries.append(("BEGIN", None))
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        self.queries.append(("COMMIT" if exc_type is None else "ROLLBACK", None))
        return False


class FakeConnection:
    def __init__(self, queries: list[tuple[str, Any]]) -> None:
        self.queries = queries

    async def execute(self, sql: str, params: Any = None) -> None:
        self.queries.append((sql, params))

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self.queries)

    async def __aenter__(self) -> FakeConnection:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


class FakePool:
    def __init__(self) -> None:
        self.queries: list[tuple[str, Any]] = []
        self.conn = FakeConnection(self.queries)

    def connection(self) -> FakeConnection:
        return self.conn


async def test_sets_tenant_context_and_commits() -> None:
    pool = FakePool()

    async with tenant_context(pool, "tenant-1"):
        pass

    statements = [query[0] for query in pool.queries]
    assert "SET LOCAL ROLE saas_app" in statements
    assert any("set_config('app.tenant_id'" in sql for sql in statements)
    assert any("set_config('app.scope'" in sql for sql in statements)
    assert statements[-1] == "COMMIT"

    params = [query[1] for query in pool.queries if query[1]]
    assert params == [["tenant-1"], ["tenant"]]


async def test_platform_scope_uses_empty_tenant_and_platform_scope() -> None:
    pool = FakePool()

    async with tenant_context(pool, None):
        pass

    params = [query[1] for query in pool.queries if query[1]]
    assert params == [[""], ["platform"]]


async def test_rolls_back_on_error() -> None:
    pool = FakePool()

    with pytest.raises(RuntimeError, match="boom"):
        async with tenant_context(pool, "tenant-1"):
            raise RuntimeError("boom")

    statements = [query[0] for query in pool.queries]
    assert "ROLLBACK" in statements
    assert "COMMIT" not in statements


async def test_uses_transaction_local_set_config() -> None:
    pool = FakePool()

    async with tenant_context(pool, "tenant-1"):
        pass

    set_configs = [query for query in pool.queries if query[0].startswith("SELECT set_config")]
    assert len(set_configs) == 2
    assert all("true" in query[0] for query in set_configs)


def test_repository_requires_transaction_handle() -> None:
    conn = FakeConnection([])

    assert Repository(conn).conn is conn

    with pytest.raises(TypeError):
        Repository()
