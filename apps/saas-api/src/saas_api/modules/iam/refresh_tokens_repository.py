from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from psycopg.rows import dict_row

from ...database.repository import Repository


@dataclass(frozen=True)
class RefreshTokenRecord:
    id: str
    user_id: str
    tenant_id: str | None
    family_id: str
    status: str
    expires_at: datetime


class RefreshTokensRepository(Repository):
    async def create(
        self,
        *,
        user_id: str,
        tenant_id: str | None,
        family_id: str,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO iam.refresh_tokens (user_id, tenant_id, family_id, token_hash, expires_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [user_id, tenant_id, family_id, token_hash, expires_at],
        )

    async def find_by_hash(self, token_hash: str) -> RefreshTokenRecord | None:
        async with self.conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT id, user_id, tenant_id, family_id, status, expires_at
                  FROM iam.refresh_tokens WHERE token_hash = %s
                """,
                [token_hash],
            )
            row = await cur.fetchone()
        if row is None:
            return None
        return RefreshTokenRecord(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            tenant_id=str(row["tenant_id"]) if row["tenant_id"] else None,
            family_id=str(row["family_id"]),
            status=str(row["status"]),
            expires_at=row["expires_at"],
        )

    async def mark_rotated(self, token_id: str) -> None:
        await self.conn.execute(
            """
            UPDATE iam.refresh_tokens SET status = 'rotated', rotated_at = now()
             WHERE id = %s AND status = 'active'
            """,
            [token_id],
        )

    async def revoke_family(self, family_id: str) -> None:
        await self.conn.execute(
            """
            UPDATE iam.refresh_tokens SET status = 'revoked', revoked_at = now()
             WHERE family_id = %s AND status <> 'revoked'
            """,
            [family_id],
        )

    async def revoke_all_for_user(self, user_id: str) -> None:
        await self.conn.execute(
            """
            UPDATE iam.refresh_tokens SET status = 'revoked', revoked_at = now()
             WHERE user_id = %s AND status <> 'revoked'
            """,
            [user_id],
        )
