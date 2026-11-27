from __future__ import annotations

from typing import Any

from psycopg_pool import AsyncConnectionPool

from ...common.config import Settings
from ...common.errors import AppError
from ...common.logging import JsonLogger
from ...database.transaction import tenant_context
from ..audit.service import AuditService
from ..auth.principal import AuthenticatedUser
from ..iam.permissions import AGENT_PERMISSIONS, TENANT_ADMIN_PERMISSIONS
from ..iam.refresh_tokens_repository import RefreshTokensRepository
from .repositories import (
    MembershipsRepository,
    RolesRepository,
    TenantsRepository,
    WorkspacesRepository,
)


class TenantService:
    def __init__(
        self,
        pool: AsyncConnectionPool,
        settings: Settings,
        logger: JsonLogger,
    ) -> None:
        self._pool = pool
        self._settings = settings
        self._audit = AuditService(pool, logger)

    # --- 租户 -----------------------------------------------------------------

    async def create_tenant(self, principal: AuthenticatedUser, name: str) -> dict[str, Any]:
        async with tenant_context(self._pool, None) as conn:
            tenants = TenantsRepository(conn)
            roles = RolesRepository(conn)
            memberships = MembershipsRepository(conn)

            tenant = await tenants.create(name)
            workspace = await WorkspacesRepository(conn).create(
                tenant.id, f"{name} 默认工作空间"
            )
            admin_role_id = await roles.create(
                tenant.id, "tenant_admin", TENANT_ADMIN_PERMISSIONS
            )
            await roles.create(tenant.id, "agent", AGENT_PERMISSIONS)
            await memberships.create(
                tenant.id, workspace.id, principal.user_id, admin_role_id
            )

        await self._audit_allow(principal, "tenant.create", "tenant", tenant.id)
        return {**tenant.to_dict(), "workspace": workspace.to_dict()}

    async def list_tenants(self, principal: AuthenticatedUser) -> list[dict[str, Any]]:
        async with tenant_context(self._pool, principal.tenant_id) as conn:
            rows = await TenantsRepository(conn).list()
        return [row.to_dict() for row in rows]

    async def get_tenant(self, principal: AuthenticatedUser, tenant_id: str) -> dict[str, Any]:
        self._assert_tenant_scope(principal, tenant_id)
        async with tenant_context(self._pool, principal.tenant_id) as conn:
            tenant = await TenantsRepository(conn).find_by_id(tenant_id)
        if tenant is None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "tenant not found")
        return tenant.to_dict()

    async def update_tenant(
        self, principal: AuthenticatedUser, tenant_id: str, name: str
    ) -> dict[str, Any]:
        self._assert_tenant_scope(principal, tenant_id)
        async with tenant_context(self._pool, principal.tenant_id) as conn:
            tenant = await TenantsRepository(conn).update_name(tenant_id, name)
        if tenant is None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "tenant not found")
        return tenant.to_dict()

    async def delete_tenant(self, principal: AuthenticatedUser, tenant_id: str) -> None:
        if principal.scope != "platform":
            raise AppError(403, "AUTH_FORBIDDEN", "platform scope required")
        async with tenant_context(self._pool, None) as conn:
            await TenantsRepository(conn).delete(tenant_id)

    # --- 工作空间 -------------------------------------------------------------

    async def list_workspaces(
        self, principal: AuthenticatedUser, tenant_id: str | None
    ) -> list[dict[str, Any]]:
        target = self._workspace_target(principal, tenant_id, required_for_platform=True)
        async with tenant_context(self._pool, target) as conn:
            rows = await WorkspacesRepository(conn).list_for_tenant(target)
        if principal.scope == "platform":
            await self._audit_allow(principal, "workspace.list", "workspace", target)
        return [row.to_dict() for row in rows]

    async def create_workspace(
        self, principal: AuthenticatedUser, name: str, tenant_id: str | None = None
    ) -> dict[str, Any]:
        target = self._workspace_target(principal, tenant_id, required_for_platform=True)
        async with tenant_context(self._pool, target) as conn:
            workspace = await WorkspacesRepository(conn).create(target, name)
            if principal.scope == "tenant":
                role = await RolesRepository(conn).find_by_name(target, "tenant_admin")
                if role is not None:
                    await MembershipsRepository(conn).create(
                        target, workspace.id, principal.user_id, role.id
                    )
        await self._audit_allow(principal, "workspace.create", "workspace", target)
        return workspace.to_dict()

    async def get_workspace(
        self, principal: AuthenticatedUser, workspace_id: str
    ) -> dict[str, Any]:
        async with tenant_context(self._pool, principal.tenant_id) as conn:
            workspace = await WorkspacesRepository(conn).find_by_id(workspace_id)
            if workspace is None:
                raise AppError(404, "RESOURCE_NOT_FOUND", "workspace not found")
            await self._assert_workspace_member(conn, principal, workspace.id)
        return workspace.to_dict()

    async def update_workspace(
        self, principal: AuthenticatedUser, workspace_id: str, name: str
    ) -> dict[str, Any]:
        async with tenant_context(self._pool, principal.tenant_id) as conn:
            workspaces = WorkspacesRepository(conn)
            workspace = await workspaces.find_by_id(workspace_id)
            if workspace is None:
                raise AppError(404, "RESOURCE_NOT_FOUND", "workspace not found")
            await self._assert_workspace_member(conn, principal, workspace.id)
            updated = await workspaces.update_name(workspace.id, name)
        if updated is None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "workspace not found")
        await self._audit_allow(
            principal, "workspace.update", "workspace", workspace.tenant_id
        )
        return updated.to_dict()

    async def delete_workspace(
        self, principal: AuthenticatedUser, workspace_id: str
    ) -> None:
        async with tenant_context(self._pool, principal.tenant_id) as conn:
            workspaces = WorkspacesRepository(conn)
            workspace = await workspaces.find_by_id(workspace_id)
            if workspace is None:
                raise AppError(404, "RESOURCE_NOT_FOUND", "workspace not found")
            await self._assert_workspace_member(conn, principal, workspace.id)
            await workspaces.delete(workspace.id)
        await self._audit_allow(
            principal, "workspace.delete", "workspace", workspace.tenant_id
        )

    # --- 成员 -----------------------------------------------------------------

    async def list_members(
        self, principal: AuthenticatedUser, workspace_id: str
    ) -> list[dict[str, Any]]:
        async with tenant_context(self._pool, principal.tenant_id) as conn:
            workspace = await WorkspacesRepository(conn).find_by_id(workspace_id)
            if workspace is None:
                raise AppError(404, "RESOURCE_NOT_FOUND", "workspace not found")
            await self._assert_workspace_member(conn, principal, workspace.id)
            members = await MembershipsRepository(conn).list_for_workspace(workspace.id)
        return [member.to_dict() for member in members]

    async def add_member(
        self,
        principal: AuthenticatedUser,
        workspace_id: str,
        user_id: str,
        role_name: str,
    ) -> dict[str, Any]:
        async with tenant_context(self._pool, principal.tenant_id) as conn:
            workspace = await WorkspacesRepository(conn).find_by_id(workspace_id)
            if workspace is None:
                raise AppError(404, "RESOURCE_NOT_FOUND", "workspace not found")
            await self._assert_workspace_member(conn, principal, workspace.id)
            role = await RolesRepository(conn).find_by_name(workspace.tenant_id, role_name)
            if role is None:
                raise AppError(400, "PARAM_INVALID", "unknown role", {"role": role_name})
            await MembershipsRepository(conn).create(
                workspace.tenant_id, workspace.id, user_id, role.id
            )
        await self._audit_allow(principal, "member.add", "membership", workspace.tenant_id)
        return {"userId": user_id, "roleName": role.name}

    async def update_member(
        self,
        principal: AuthenticatedUser,
        workspace_id: str,
        user_id: str,
        role_name: str,
    ) -> dict[str, Any]:
        async with tenant_context(self._pool, principal.tenant_id) as conn:
            workspace = await WorkspacesRepository(conn).find_by_id(workspace_id)
            if workspace is None:
                raise AppError(404, "RESOURCE_NOT_FOUND", "workspace not found")
            await self._assert_workspace_member(conn, principal, workspace.id)
            role = await RolesRepository(conn).find_by_name(workspace.tenant_id, role_name)
            if role is None:
                raise AppError(400, "PARAM_INVALID", "unknown role", {"role": role_name})
            updated = await MembershipsRepository(conn).update_role(
                workspace.id, user_id, role.id
            )
        if not updated:
            raise AppError(404, "RESOURCE_NOT_FOUND", "member not found")
        await self._audit_allow(
            principal, "member.update", "membership", workspace.tenant_id
        )
        return {"userId": user_id, "roleName": role.name}

    async def remove_member(
        self, principal: AuthenticatedUser, workspace_id: str, user_id: str
    ) -> None:
        async with tenant_context(self._pool, principal.tenant_id) as conn:
            workspace = await WorkspacesRepository(conn).find_by_id(workspace_id)
            if workspace is None:
                raise AppError(404, "RESOURCE_NOT_FOUND", "workspace not found")
            await self._assert_workspace_member(conn, principal, workspace.id)
            await MembershipsRepository(conn).delete(workspace.id, user_id)
            await RefreshTokensRepository(conn).revoke_all_for_user(user_id)
        await self._audit_allow(
            principal, "member.remove", "membership", workspace.tenant_id
        )

    # --- 内部 -----------------------------------------------------------------

    def _workspace_target(
        self,
        principal: AuthenticatedUser,
        tenant_id: str | None,
        *,
        required_for_platform: bool,
    ) -> str:
        if principal.scope == "platform":
            if required_for_platform and not tenant_id:
                raise AppError(
                    400, "PARAM_INVALID", "tenant_id is required for platform scope"
                )
            if tenant_id:
                return tenant_id
            raise AppError(400, "PARAM_INVALID", "tenant_id is required for platform scope")

        if tenant_id and tenant_id != principal.tenant_id:
            raise AppError(403, "TENANT_SCOPE_MISMATCH", "requested tenant is not in scope")
        if principal.tenant_id is None:
            raise AppError(403, "AUTH_FORBIDDEN", "tenant context required")
        return principal.tenant_id

    def _assert_tenant_scope(self, principal: AuthenticatedUser, tenant_id: str) -> None:
        if principal.scope == "tenant" and principal.tenant_id != tenant_id:
            raise AppError(403, "TENANT_SCOPE_MISMATCH", "requested tenant is not in scope")

    async def _assert_workspace_member(
        self, conn: Any, principal: AuthenticatedUser, workspace_id: str
    ) -> None:
        if principal.scope != "tenant":
            return
        if not await MembershipsRepository(conn).is_member(workspace_id, principal.user_id):
            raise AppError(403, "AUTH_FORBIDDEN", "not a workspace member")

    async def _audit_allow(
        self,
        principal: AuthenticatedUser,
        action: str,
        resource_type: str,
        tenant_id: str | None,
    ) -> None:
        await self._audit.record(
            actor_type="user",
            actor_id=principal.user_id,
            action=action,
            resource_type=resource_type,
            decision="allow",
            tenant_id=tenant_id,
        )
