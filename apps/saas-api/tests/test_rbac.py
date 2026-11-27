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
    fetch_all,
    fetch_one,
    login_as,
)

pytestmark = pytest.mark.usefixtures("clean_db")


async def seed(
    admin_pool: AsyncConnectionPool, password_hash: str, email: str
) -> dict[str, Any]:
    tenant = await create_tenant(
        admin_pool, "Acme", workspace_name=lambda suffix: f"WS-{suffix}"
    )
    user_id = await create_user(admin_pool, password_hash, email)
    await add_membership(
        admin_pool,
        tenant_id=tenant["tenant_id"],
        workspace_id=tenant["workspace_ids"][0],
        user_id=user_id,
        role_id=tenant["agent_role_id"],
    )
    return {**tenant, "user_id": user_id}


async def test_read_only_role_can_read_but_cannot_write(
    db_call: Call, admin_pool: AsyncConnectionPool, password_hash: str
) -> None:
    seeded = await seed(admin_pool, password_hash, "agent@poc.test")
    token = auth(await login_as(db_call, "agent@poc.test"))
    workspace_id = seeded["workspace_ids"][0]

    assert (await db_call("GET", "/api/v1/tenants", headers=token)).status_code == 200
    assert (await db_call("GET", "/api/v1/workspaces", headers=token)).status_code == 200
    assert (
        await db_call("GET", f"/api/v1/workspaces/{workspace_id}", headers=token)
    ).status_code == 200

    denied = [
        await db_call("POST", "/api/v1/tenants", headers=token, json={"name": "X"}),
        await db_call("POST", "/api/v1/workspaces", headers=token, json={"name": "X"}),
        await db_call(
            "PATCH",
            f"/api/v1/workspaces/{workspace_id}",
            headers=token,
            json={"name": "Y"},
        ),
        await db_call("DELETE", f"/api/v1/workspaces/{workspace_id}", headers=token),
        await db_call(
            "POST",
            f"/api/v1/workspaces/{workspace_id}/members",
            headers=token,
            json={"user_id": seeded["tenant_id"]},
        ),
    ]

    for response in denied:
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "AUTH_FORBIDDEN"

    audit = await fetch_all(
        admin_pool,
        """
        SELECT 1 FROM audit.audit_logs
         WHERE action = 'authorize' AND decision = 'deny' AND tenant_id = %s
        """,
        [seeded["tenant_id"]],
    )
    assert len(audit) >= len(denied)


async def test_permission_without_workspace_membership_cannot_write(
    db_call: Call, admin_pool: AsyncConnectionPool, password_hash: str
) -> None:
    seeded = await create_tenant(
        admin_pool, "Acme", workspace_name=lambda suffix: f"WS-{suffix}"
    )
    workspace_a, workspace_b = seeded["workspace_ids"]

    admin_id = await create_user(admin_pool, password_hash, "admin@poc.test")
    await add_membership(
        admin_pool,
        tenant_id=seeded["tenant_id"],
        workspace_id=workspace_a,
        user_id=admin_id,
        role_id=seeded["admin_role_id"],
    )

    token = auth(await login_as(db_call, "admin@poc.test"))
    response = await db_call(
        "PATCH",
        f"/api/v1/workspaces/{workspace_b}",
        headers=token,
        json={"name": "hijacked"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_FORBIDDEN"
    assert "data" not in response.json()

    workspace = await fetch_one(
        admin_pool, "SELECT name FROM tenant.workspaces WHERE id = %s", [workspace_b]
    )
    assert workspace is not None and workspace["name"] == "WS-b"
