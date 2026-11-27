from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from ...common.logging import JsonLogger
from ...database.transaction import tenant_context


class AuditService:
    def __init__(self, pool: AsyncConnectionPool, logger: JsonLogger) -> None:
        self._pool = pool
        self._logger = logger

    async def record(
        self,
        *,
        actor_type: str,
        actor_id: str | None,
        action: str,
        resource_type: str,
        decision: str,
        details: dict[str, Any] | None = None,
        tenant_id: str | None = None,
    ) -> None:
        try:
            async with tenant_context(self._pool, tenant_id) as conn:
                await conn.execute(
                    """
                    INSERT INTO audit.audit_logs
                      (actor_type, actor_id, action, resource_type, resource_id,
                       tenant_id, workspace_id, decision, details)
                    VALUES (%s, %s, %s, %s, NULL, %s, NULL, %s, %s)
                    """,
                    [
                        actor_type,
                        actor_id,
                        action,
                        resource_type,
                        tenant_id,
                        decision,
                        Jsonb(details or {}),
                    ],
                )
        except Exception as error:  # 审计失败不应让业务请求失败
            self._logger.warn("AUDIT_WRITE_FAILED", str(error), action=action)
