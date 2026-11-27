from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection


class Repository:
    """薄 repository 基类：事务句柄必须由调用方传入，禁止自行取连接。"""

    def __init__(self, conn: AsyncConnection[Any]) -> None:
        self._conn = conn

    @property
    def conn(self) -> AsyncConnection[Any]:
        return self._conn
