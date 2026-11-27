from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psycopg.rows import dict_row

from ...database.repository import Repository

USER_COLUMNS = "id, email, display_name, password_hash, status, is_platform_admin"


@dataclass(frozen=True)
class UserRecord:
    id: str
    email: str
    display_name: str
    password_hash: str
    status: str
    is_platform_admin: bool


def _to_record(row: dict[str, Any]) -> UserRecord:
    return UserRecord(
        id=str(row["id"]),
        email=str(row["email"]),
        display_name=str(row["display_name"]),
        password_hash=str(row["password_hash"]),
        status=str(row["status"]),
        is_platform_admin=bool(row["is_platform_admin"]),
    )


class UsersRepository(Repository):
    async def find_by_email(self, email: str) -> UserRecord | None:
        async with self.conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                f"SELECT {USER_COLUMNS} FROM iam.users WHERE lower(email) = lower(%s)",
                [email],
            )
            row = await cur.fetchone()
        return _to_record(row) if row else None

    async def find_by_id(self, user_id: str) -> UserRecord | None:
        async with self.conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                f"SELECT {USER_COLUMNS} FROM iam.users WHERE id = %s", [user_id]
            )
            row = await cur.fetchone()
        return _to_record(row) if row else None

    async def tenant_ids_for(self, user_id: str) -> list[str]:
        async with self.conn.cursor() as cur:
            await cur.execute(
                """
                SELECT DISTINCT tenant_id FROM iam.memberships
                 WHERE user_id = %s ORDER BY tenant_id
                """,
                [user_id],
            )
            return [str(row[0]) for row in await cur.fetchall()]

    async def permissions_for(self, user_id: str, tenant_id: str) -> list[str]:
        async with self.conn.cursor() as cur:
            await cur.execute(
                """
                SELECT DISTINCT rp.permission_key
                  FROM iam.memberships m
                  JOIN iam.role_permissions rp ON rp.role_id = m.role_id
                 WHERE m.user_id = %s AND m.tenant_id = %s
                 ORDER BY rp.permission_key
                """,
                [user_id, tenant_id],
            )
            return [str(row[0]) for row in await cur.fetchall()]
