from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psycopg.rows import dict_row

from ...database.repository import Repository


@dataclass(frozen=True)
class TenantRecord:
    id: str
    name: str
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "status": self.status}


@dataclass(frozen=True)
class WorkspaceRecord:
    id: str
    tenant_id: str
    name: str
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenantId": self.tenant_id,
            "name": self.name,
            "status": self.status,
        }


@dataclass(frozen=True)
class RoleRecord:
    id: str
    name: str


@dataclass(frozen=True)
class MemberRecord:
    user_id: str
    display_name: str
    role_name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "userId": self.user_id,
            "displayName": self.display_name,
            "roleName": self.role_name,
        }


class TenantsRepository(Repository):
    async def create(self, name: str) -> TenantRecord:
        async with self.conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "INSERT INTO tenant.tenants (name) VALUES (%s) RETURNING id, name, status",
                [name],
            )
            row = await cur.fetchone()
        if row is None:
            raise RuntimeError("tenant insert returned no row")
        return TenantRecord(str(row["id"]), str(row["name"]), str(row["status"]))

    async def find_by_id(self, tenant_id: str) -> TenantRecord | None:
        async with self.conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id, name, status FROM tenant.tenants WHERE id = %s", [tenant_id]
            )
            row = await cur.fetchone()
        if row is None:
            return None
        return TenantRecord(str(row["id"]), str(row["name"]), str(row["status"]))

    async def list(self) -> list[TenantRecord]:
        async with self.conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("SELECT id, name, status FROM tenant.tenants ORDER BY name")
            rows = await cur.fetchall()
        return [
            TenantRecord(str(row["id"]), str(row["name"]), str(row["status"])) for row in rows
        ]

    async def update_name(self, tenant_id: str, name: str) -> TenantRecord | None:
        async with self.conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                UPDATE tenant.tenants SET name = %s, updated_at = now()
                 WHERE id = %s RETURNING id, name, status
                """,
                [name, tenant_id],
            )
            row = await cur.fetchone()
        if row is None:
            return None
        return TenantRecord(str(row["id"]), str(row["name"]), str(row["status"]))

    async def delete(self, tenant_id: str) -> None:
        await self.conn.execute("DELETE FROM tenant.tenants WHERE id = %s", [tenant_id])


class WorkspacesRepository(Repository):
    async def create(self, tenant_id: str, name: str) -> WorkspaceRecord:
        async with self.conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO tenant.workspaces (tenant_id, name)
                VALUES (%s, %s) RETURNING id, tenant_id, name, status
                """,
                [tenant_id, name],
            )
            row = await cur.fetchone()
        if row is None:
            raise RuntimeError("workspace insert returned no row")
        return _workspace(row)

    async def find_by_id(self, workspace_id: str) -> WorkspaceRecord | None:
        async with self.conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT id, tenant_id, name, status FROM tenant.workspaces WHERE id = %s
                """,
                [workspace_id],
            )
            row = await cur.fetchone()
        return _workspace(row) if row else None

    async def list_for_tenant(self, tenant_id: str) -> list[WorkspaceRecord]:
        async with self.conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT id, tenant_id, name, status FROM tenant.workspaces
                 WHERE tenant_id = %s ORDER BY name
                """,
                [tenant_id],
            )
            rows = await cur.fetchall()
        return [_workspace(row) for row in rows]

    async def update_name(self, workspace_id: str, name: str) -> WorkspaceRecord | None:
        async with self.conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                UPDATE tenant.workspaces SET name = %s, updated_at = now()
                 WHERE id = %s RETURNING id, tenant_id, name, status
                """,
                [name, workspace_id],
            )
            row = await cur.fetchone()
        return _workspace(row) if row else None

    async def delete(self, workspace_id: str) -> None:
        await self.conn.execute("DELETE FROM tenant.workspaces WHERE id = %s", [workspace_id])


def _workspace(row: dict[str, Any]) -> WorkspaceRecord:
    return WorkspaceRecord(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"]),
        name=str(row["name"]),
        status=str(row["status"]),
    )


class RolesRepository(Repository):
    async def create(
        self, tenant_id: str, name: str, permissions: tuple[str, ...]
    ) -> str:
        async with self.conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO iam.roles (tenant_id, name) VALUES (%s, %s) RETURNING id",
                [tenant_id, name],
            )
            row = await cur.fetchone()
        if row is None:
            raise RuntimeError("role insert returned no row")
        role_id = str(row[0])
        for permission in permissions:
            await self.conn.execute(
                """
                INSERT INTO iam.role_permissions (role_id, permission_key)
                VALUES (%s, %s) ON CONFLICT DO NOTHING
                """,
                [role_id, permission],
            )
        return role_id

    async def find_by_name(self, tenant_id: str, name: str) -> RoleRecord | None:
        async with self.conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id, name FROM iam.roles WHERE tenant_id = %s AND name = %s",
                [tenant_id, name],
            )
            row = await cur.fetchone()
        if row is None:
            return None
        return RoleRecord(str(row["id"]), str(row["name"]))


class MembershipsRepository(Repository):
    async def create(
        self, tenant_id: str, workspace_id: str, user_id: str, role_id: str
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO iam.memberships (tenant_id, workspace_id, user_id, role_id)
            VALUES (%s, %s, %s, %s)
            """,
            [tenant_id, workspace_id, user_id, role_id],
        )

    async def is_member(self, workspace_id: str, user_id: str) -> bool:
        async with self.conn.cursor() as cur:
            await cur.execute(
                "SELECT 1 FROM iam.memberships WHERE workspace_id = %s AND user_id = %s",
                [workspace_id, user_id],
            )
            return await cur.fetchone() is not None

    async def update_role(self, workspace_id: str, user_id: str, role_id: str) -> bool:
        async with self.conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE iam.memberships SET role_id = %s
                 WHERE workspace_id = %s AND user_id = %s
                """,
                [role_id, workspace_id, user_id],
            )
            return cur.rowcount > 0

    async def delete(self, workspace_id: str, user_id: str) -> None:
        await self.conn.execute(
            "DELETE FROM iam.memberships WHERE workspace_id = %s AND user_id = %s",
            [workspace_id, user_id],
        )

    async def list_for_workspace(self, workspace_id: str) -> list[MemberRecord]:
        async with self.conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT m.user_id, u.display_name, r.name AS role_name
                  FROM iam.memberships m
                  JOIN iam.users u ON u.id = m.user_id
                  JOIN iam.roles r ON r.id = m.role_id
                 WHERE m.workspace_id = %s
                 ORDER BY u.email
                """,
                [workspace_id],
            )
            rows = await cur.fetchall()
        return [
            MemberRecord(
                user_id=str(row["user_id"]),
                display_name=str(row["display_name"]),
                role_name=str(row["role_name"]),
            )
            for row in rows
        ]
