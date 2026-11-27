from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from psycopg_pool import AsyncConnectionPool

from ...common.dependencies import logger_of, pool_of
from ...common.errors import AppError
from ...database.transaction import tenant_context
from ..audit.service import AuditService
from ..iam.permissions import PLATFORM_PERMISSIONS
from ..iam.users_repository import UsersRepository
from .dependencies import require_principal
from .principal import AuthenticatedUser


async def current_permissions(
    pool: AsyncConnectionPool, principal: AuthenticatedUser
) -> set[str]:
    if principal.scope == "platform":
        async with tenant_context(pool, None) as conn:
            user = await UsersRepository(conn).find_by_id(principal.user_id)
        return set(PLATFORM_PERMISSIONS) if user and user.is_platform_admin else set()

    if not principal.tenant_id:
        return set()

    async with tenant_context(pool, principal.tenant_id) as conn:
        permissions = await UsersRepository(conn).permissions_for(
            principal.user_id, principal.tenant_id
        )
    return set(permissions)


async def _deny(request: Request, principal: AuthenticatedUser, missing: list[str]) -> None:
    await AuditService(pool_of(request), logger_of(request)).record(
        actor_type="user",
        actor_id=principal.user_id,
        action="authorize",
        resource_type="route",
        decision="deny",
        tenant_id=principal.tenant_id,
        details={"missing": missing},
    )
    raise AppError(
        403,
        "AUTH_FORBIDDEN",
        "insufficient permissions",
        {"missing": missing},
    )


def require_permission(
    permission: str,
) -> Callable[..., Awaitable[AuthenticatedUser]]:
    async def dependency(
        request: Request,
        principal: Annotated[AuthenticatedUser, Depends(require_principal)],
    ) -> AuthenticatedUser:
        current = await current_permissions(pool_of(request), principal)
        if permission not in current:
            await _deny(request, principal, [permission])
        return principal

    return dependency


async def require_platform_manager(
    request: Request,
    principal: Annotated[AuthenticatedUser, Depends(require_principal)],
) -> AuthenticatedUser:
    current = await current_permissions(pool_of(request), principal)
    if principal.scope != "platform" or "tenant:manage" not in current:
        await _deny(request, principal, ["tenant:manage"])
    return principal
