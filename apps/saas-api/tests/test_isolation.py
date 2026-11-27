from __future__ import annotations

from typing import Any

import pytest
from psycopg_pool import AsyncConnectionPool

from support import (
    Call,
    add_membership,
    auth,
    create_tenant,
    create_user,
    fetch_one,
    login_as,
)

pytestmark = pytest.mark.usefixtures("clean_db")


async def build_tenant(
    admin_pool: AsyncConnectionPool, password_hash: str, label: str
) -> dict[str, Any]:
    tenant = await create_tenant(
        admin_pool,
        f"Tenant {label}",
        suffixes=("1", "2"),
        workspace_name=lambda suffix: f"{label}-ws-{suffix}",
    )
    email = f"admin-{label}@poc.test"
    user_id = await create_user(admin_pool, password_hash, email)
    await add_membership(
        admin_pool,
        tenant_id=tenant["tenant_id"],
        workspace_id=tenant["workspace_ids"][0],
        user_id=user_id,
        role_id=tenant["admin_role_id"],
    )
    return {
        "tenant_id": tenant["tenant_id"],
        "workspace_ids": tenant["workspace_ids"],
        "email": email,
    }


@pytest.fixture
async def matrix(
    admin_pool: AsyncConnectionPool, db_call: Call, password_hash: str
) -> dict[str, Any]:
    alpha = await build_tenant(admin_pool, password_hash, "alpha")
    beta = await build_tenant(admin_pool, password_hash, "beta")
    alpha_token = await login_as(db_call, alpha["email"])
    beta_token = await login_as(db_call, beta["email"])
    return {
        "alpha": alpha,
        "beta": beta,
        "alpha_token": alpha_token,
        "beta_token": beta_token,
    }


async def test_reads_across_tenant_and_workspace_are_denied(
    db_call: Call, matrix: dict[str, Any]
) -> None:
    alpha = matrix["alpha"]
    beta = matrix["beta"]
    token = auth(matrix["alpha_token"])

    cases = [
        await db_call("GET", f"/api/v1/tenants/{beta['tenant_id']}", headers=token),
        await db_call("GET", f"/api/v1/workspaces/{beta['workspace_ids'][0]}", headers=token),
        await db_call("GET", f"/api/v1/workspaces/{alpha['workspace_ids'][1]}", headers=token),
        await db_call(
            "GET", f"/api/v1/workspaces?tenant_id={beta['tenant_id']}", headers=token
        ),
        await db_call(
            "GET",
            f"/api/v1/workspaces/{beta['workspace_ids'][0]}/members",
            headers=token,
        ),
    ]

    for response in cases:
        assert response.status_code in (403, 404)
        assert "data" not in response.json()


async def test_writes_across_tenant_and_workspace_are_denied_and_data_unchanged(
    db_call: Call, admin_pool: AsyncConnectionPool, matrix: dict[str, Any]
) -> None:
    beta = matrix["beta"]
    token = auth(matrix["alpha_token"])

    cases = [
        await db_call(
            "PATCH",
            f"/api/v1/tenants/{beta['tenant_id']}",
            headers=token,
            json={"name": "hijacked"},
        ),
        await db_call(
            "PATCH",
            f"/api/v1/workspaces/{beta['workspace_ids'][0]}",
            headers=token,
            json={"name": "hijacked"},
        ),
        await db_call(
            "DELETE", f"/api/v1/workspaces/{beta['workspace_ids'][0]}", headers=token
        ),
        await db_call(
            "POST",
            f"/api/v1/workspaces/{beta['workspace_ids'][0]}/members",
            headers=token,
            json={"user_id": matrix["alpha"]["workspace_ids"][0], "role": "agent"},
        ),
    ]

    for response in cases:
        assert response.status_code in (403, 404)

    tenant_row = await fetch_one(
        admin_pool, "SELECT name FROM tenant.tenants WHERE id = %s", [beta["tenant_id"]]
    )
    assert tenant_row is not None and tenant_row["name"] == "Tenant beta"

    workspace_row = await fetch_one(
        admin_pool,
        "SELECT name FROM tenant.workspaces WHERE id = %s",
        [beta["workspace_ids"][0]],
    )
    assert workspace_row is not None and workspace_row["name"] == "beta-ws-1"


async def test_lists_only_return_own_tenant_resources(
    db_call: Call, matrix: dict[str, Any]
) -> None:
    alpha = matrix["alpha"]
    token = auth(matrix["alpha_token"])

    tenants = await db_call("GET", "/api/v1/tenants", headers=token)
    assert tenants.status_code == 200
    assert [row["id"] for row in tenants.json()["data"]] == [alpha["tenant_id"]]

    workspaces = await db_call("GET", "/api/v1/workspaces", headers=token)
    assert workspaces.status_code == 200
    assert len(workspaces.json()["data"]) == 2
    assert all(row["tenantId"] == alpha["tenant_id"] for row in workspaces.json()["data"])


async def test_reverse_direction_also_holds(db_call: Call, matrix: dict[str, Any]) -> None:
    alpha = matrix["alpha"]
    response = await db_call(
        "GET",
        f"/api/v1/workspaces/{alpha['workspace_ids'][0]}",
        headers=auth(matrix["beta_token"]),
    )

    assert response.status_code in (403, 404)
