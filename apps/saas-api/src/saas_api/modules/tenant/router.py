from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

from ...common.dependencies import logger_of, pool_of, settings_of
from ...common.envelope import envelope
from ..auth.guards import require_permission, require_platform_manager
from ..auth.principal import AuthenticatedUser
from .dto import (
    AddMemberRequest,
    CreateTenantRequest,
    CreateWorkspaceRequest,
    UpdateMemberRequest,
    UpdateTenantRequest,
    UpdateWorkspaceRequest,
)
from .service import TenantService

router = APIRouter()


def _service(request: Request) -> TenantService:
    return TenantService(pool_of(request), settings_of(request), logger_of(request))


@router.post("/tenants", status_code=201)
async def create_tenant(
    body: CreateTenantRequest,
    request: Request,
    principal: Annotated[AuthenticatedUser, Depends(require_platform_manager)],
) -> dict[str, Any]:
    return envelope(await _service(request).create_tenant(principal, body.name))


@router.get("/tenants")
async def list_tenants(
    request: Request,
    principal: Annotated[AuthenticatedUser, Depends(require_permission("tenant:read"))],
) -> dict[str, Any]:
    return envelope(await _service(request).list_tenants(principal))


@router.get("/tenants/{tenant_id}")
async def get_tenant(
    tenant_id: uuid.UUID,
    request: Request,
    principal: Annotated[AuthenticatedUser, Depends(require_permission("tenant:read"))],
) -> dict[str, Any]:
    return envelope(await _service(request).get_tenant(principal, str(tenant_id)))


@router.patch("/tenants/{tenant_id}")
async def update_tenant(
    tenant_id: uuid.UUID,
    body: UpdateTenantRequest,
    request: Request,
    principal: Annotated[AuthenticatedUser, Depends(require_permission("tenant:manage"))],
) -> dict[str, Any]:
    return envelope(
        await _service(request).update_tenant(principal, str(tenant_id), body.name)
    )


@router.delete("/tenants/{tenant_id}", status_code=204)
async def delete_tenant(
    tenant_id: uuid.UUID,
    request: Request,
    principal: Annotated[AuthenticatedUser, Depends(require_permission("tenant:manage"))],
) -> Response:
    await _service(request).delete_tenant(principal, str(tenant_id))
    return Response(status_code=204)


@router.get("/workspaces")
async def list_workspaces(
    request: Request,
    principal: Annotated[AuthenticatedUser, Depends(require_permission("workspace:read"))],
    tenant_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    target = str(tenant_id) if tenant_id else None
    return envelope(await _service(request).list_workspaces(principal, target))


@router.post("/workspaces", status_code=201)
async def create_workspace(
    body: CreateWorkspaceRequest,
    request: Request,
    principal: Annotated[AuthenticatedUser, Depends(require_permission("workspace:manage"))],
    tenant_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    target = str(tenant_id) if tenant_id else None
    return envelope(await _service(request).create_workspace(principal, body.name, target))


@router.get("/workspaces/{workspace_id}")
async def get_workspace(
    workspace_id: uuid.UUID,
    request: Request,
    principal: Annotated[AuthenticatedUser, Depends(require_permission("workspace:read"))],
) -> dict[str, Any]:
    return envelope(await _service(request).get_workspace(principal, str(workspace_id)))


@router.patch("/workspaces/{workspace_id}")
async def update_workspace(
    workspace_id: uuid.UUID,
    body: UpdateWorkspaceRequest,
    request: Request,
    principal: Annotated[AuthenticatedUser, Depends(require_permission("workspace:manage"))],
) -> dict[str, Any]:
    return envelope(
        await _service(request).update_workspace(principal, str(workspace_id), body.name)
    )


@router.delete("/workspaces/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: uuid.UUID,
    request: Request,
    principal: Annotated[AuthenticatedUser, Depends(require_permission("workspace:manage"))],
) -> Response:
    await _service(request).delete_workspace(principal, str(workspace_id))
    return Response(status_code=204)


@router.get("/workspaces/{workspace_id}/members")
async def list_members(
    workspace_id: uuid.UUID,
    request: Request,
    principal: Annotated[AuthenticatedUser, Depends(require_permission("workspace:read"))],
) -> dict[str, Any]:
    return envelope(await _service(request).list_members(principal, str(workspace_id)))


@router.post("/workspaces/{workspace_id}/members", status_code=201)
async def add_member(
    workspace_id: uuid.UUID,
    body: AddMemberRequest,
    request: Request,
    principal: Annotated[AuthenticatedUser, Depends(require_permission("member:manage"))],
) -> dict[str, Any]:
    return envelope(
        await _service(request).add_member(
            principal, str(workspace_id), str(body.user_id), body.role
        )
    )


@router.patch("/workspaces/{workspace_id}/members/{user_id}")
async def update_member(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    body: UpdateMemberRequest,
    request: Request,
    principal: Annotated[AuthenticatedUser, Depends(require_permission("member:manage"))],
) -> dict[str, Any]:
    return envelope(
        await _service(request).update_member(
            principal, str(workspace_id), str(user_id), body.role
        )
    )


@router.delete("/workspaces/{workspace_id}/members/{user_id}", status_code=204)
async def remove_member(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
    principal: Annotated[AuthenticatedUser, Depends(require_permission("member:manage"))],
) -> Response:
    await _service(request).remove_member(principal, str(workspace_id), str(user_id))
    return Response(status_code=204)
