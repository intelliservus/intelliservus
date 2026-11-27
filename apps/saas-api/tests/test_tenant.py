from __future__ import annotations

import pytest
from psycopg_pool import AsyncConnectionPool

from support import (
    Call,
    add_membership,
    auth,
    create_tenant,
    create_user,
    fetch_all,
    login_as,
)

pytestmark = pytest.mark.usefixtures("clean_db")


async def test_platform_admin_creates_tenant_with_workspace_roles_and_membership(
    db_call: Call, admin_pool: AsyncConnectionPool, password_hash: str
) -> None:
    await create_user(admin_pool, password_hash, "platform@poc.test", platform_admin=True)
    token = await login_as(db_call, "platform@poc.test")

    response = await db_call(
        "POST", "/api/v1/tenants", headers=auth(token), json={"name": "Acme"}
    )

    assert response.status_code == 201
    body = response.json()["data"]
    assert body["name"] == "Acme"
    assert body["workspace"]["id"]

    tenant_id = body["id"]
    roles = await fetch_all(
        admin_pool,
        "SELECT name FROM iam.roles WHERE tenant_id = %s ORDER BY name",
        [tenant_id],
    )
    assert [row["name"] for row in roles] == ["agent", "tenant_admin"]

    memberships = await fetch_all(
        admin_pool,
        "SELECT 1 FROM iam.memberships WHERE tenant_id = %s AND workspace_id = %s",
        [tenant_id, body["workspace"]["id"]],
    )
    assert len(memberships) == 1

    audit = await fetch_all(
        admin_pool,
        "SELECT 1 FROM audit.audit_logs WHERE action = 'tenant.create' AND tenant_id = %s",
        [tenant_id],
    )
    assert len(audit) == 1


async def test_tenant_admin_cannot_create_tenant(
    db_call: Call, admin_pool: AsyncConnectionPool, password_hash: str
) -> None:
    user_id = await create_user(admin_pool, password_hash, "admin@poc.test")
    tenant = await create_tenant(admin_pool, "Acme")
    await add_membership(
        admin_pool,
        tenant_id=tenant["tenant_id"],
        workspace_id=tenant["workspace_ids"][0],
        user_id=user_id,
        role_id=tenant["admin_role_id"],
    )

    token = await login_as(db_call, "admin@poc.test")
    response = await db_call(
        "POST", "/api/v1/tenants", headers=auth(token), json={"name": "Escalate"}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_FORBIDDEN"


async def test_tenant_user_only_sees_own_tenant_and_workspaces(
    db_call: Call, admin_pool: AsyncConnectionPool, password_hash: str
) -> None:
    user_id = await create_user(admin_pool, password_hash, "admin@poc.test")
    own = await create_tenant(admin_pool, "Acme")
    await create_tenant(admin_pool, "Globex")
    await add_membership(
        admin_pool,
        tenant_id=own["tenant_id"],
        workspace_id=own["workspace_ids"][0],
        user_id=user_id,
        role_id=own["admin_role_id"],
    )

    token = await login_as(db_call, "admin@poc.test")

    tenants = await db_call("GET", "/api/v1/tenants", headers=auth(token))
    assert tenants.status_code == 200
    assert len(tenants.json()["data"]) == 1
    assert tenants.json()["data"][0]["name"] == "Acme"

    workspaces = await db_call("GET", "/api/v1/workspaces", headers=auth(token))
    assert workspaces.status_code == 200
    assert len(workspaces.json()["data"]) == 2


async def test_cross_tenant_read_returns_scope_mismatch(
    db_call: Call, admin_pool: AsyncConnectionPool, password_hash: str
) -> None:
    user_id = await create_user(admin_pool, password_hash, "admin@poc.test")
    own = await create_tenant(admin_pool, "Acme")
    other = await create_tenant(admin_pool, "Globex")
    await add_membership(
        admin_pool,
        tenant_id=own["tenant_id"],
        workspace_id=own["workspace_ids"][0],
        user_id=user_id,
        role_id=own["admin_role_id"],
    )

    token = await login_as(db_call, "admin@poc.test")
    response = await db_call(
        "GET", f"/api/v1/tenants/{other['tenant_id']}", headers=auth(token)
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "TENANT_SCOPE_MISMATCH"


async def test_same_tenant_cross_workspace_is_denied(
    db_call: Call, admin_pool: AsyncConnectionPool, password_hash: str
) -> None:
    user_id = await create_user(admin_pool, password_hash, "admin@poc.test")
    own = await create_tenant(admin_pool, "Acme")
    await add_membership(
        admin_pool,
        tenant_id=own["tenant_id"],
        workspace_id=own["workspace_ids"][0],
        user_id=user_id,
        role_id=own["admin_role_id"],
    )

    token = await login_as(db_call, "admin@poc.test")
    response = await db_call(
        "GET", f"/api/v1/workspaces/{own['workspace_ids'][1]}", headers=auth(token)
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_FORBIDDEN"


async def test_platform_admin_cross_tenant_requires_tenant_id_and_writes_audit(
    db_call: Call, admin_pool: AsyncConnectionPool, password_hash: str
) -> None:
    user_id = await create_user(admin_pool, password_hash, "platform@poc.test", platform_admin=True)
    tenant = await create_tenant(admin_pool, "Acme")
    token = await login_as(db_call, "platform@poc.test")

    without_tenant = await db_call("GET", "/api/v1/workspaces", headers=auth(token))
    assert without_tenant.status_code == 400
    assert without_tenant.json()["error"]["code"] == "PARAM_INVALID"

    with_tenant = await db_call(
        "GET", f"/api/v1/workspaces?tenant_id={tenant['tenant_id']}", headers=auth(token)
    )
    assert with_tenant.status_code == 200
    assert len(with_tenant.json()["data"]) == 2

    audit = await fetch_all(
        admin_pool,
        """
        SELECT 1 FROM audit.audit_logs
         WHERE action = 'workspace.list' AND tenant_id = %s AND actor_id = %s
        """,
        [tenant["tenant_id"], user_id],
    )
    assert len(audit) == 1


async def test_removed_member_loses_access_and_refresh_tokens_are_revoked(
    db_call: Call, admin_pool: AsyncConnectionPool, password_hash: str
) -> None:
    admin = await create_user(admin_pool, password_hash, "admin@poc.test")
    member = await create_user(admin_pool, password_hash, "member@poc.test")
    tenant = await create_tenant(admin_pool, "Acme")
    workspace_id = tenant["workspace_ids"][0]

    await add_membership(
        admin_pool,
        tenant_id=tenant["tenant_id"],
        workspace_id=workspace_id,
        user_id=admin,
        role_id=tenant["admin_role_id"],
    )
    await add_membership(
        admin_pool,
        tenant_id=tenant["tenant_id"],
        workspace_id=workspace_id,
        user_id=member,
        role_id=tenant["admin_role_id"],
    )

    admin_token = await login_as(db_call, "admin@poc.test")
    member_token = await login_as(db_call, "member@poc.test")

    before = await db_call("GET", f"/api/v1/workspaces/{workspace_id}", headers=auth(member_token))
    assert before.status_code == 200

    removed = await db_call(
        "DELETE",
        f"/api/v1/workspaces/{workspace_id}/members/{member}",
        headers=auth(admin_token),
    )
    assert removed.status_code == 204

    after = await db_call("GET", f"/api/v1/workspaces/{workspace_id}", headers=auth(member_token))
    assert after.status_code == 403
    assert after.json()["error"]["code"] == "AUTH_FORBIDDEN"

    tokens = await fetch_all(
        admin_pool,
        "SELECT status FROM iam.refresh_tokens WHERE user_id = %s",
        [member],
    )
    assert len(tokens) > 0
    assert all(row["status"] == "revoked" for row in tokens)


async def test_workspace_and_member_crud(
    db_call: Call, admin_pool: AsyncConnectionPool, password_hash: str
) -> None:
    user_id = await create_user(admin_pool, password_hash, "admin@poc.test")
    tenant = await create_tenant(admin_pool, "Acme")
    await add_membership(
        admin_pool,
        tenant_id=tenant["tenant_id"],
        workspace_id=tenant["workspace_ids"][0],
        user_id=user_id,
        role_id=tenant["admin_role_id"],
    )
    member = await create_user(admin_pool, password_hash, "member@poc.test")

    token = await login_as(db_call, "admin@poc.test")

    created = await db_call(
        "POST", "/api/v1/workspaces", headers=auth(token), json={"name": "Support"}
    )
    assert created.status_code == 201
    workspace_id = created.json()["data"]["id"]

    added = await db_call(
        "POST",
        f"/api/v1/workspaces/{workspace_id}/members",
        headers=auth(token),
        json={"user_id": member, "role": "agent"},
    )
    assert added.status_code == 201
    assert added.json()["data"]["roleName"] == "agent"

    updated = await db_call(
        "PATCH",
        f"/api/v1/workspaces/{workspace_id}/members/{member}",
        headers=auth(token),
        json={"role": "tenant_admin"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["roleName"] == "tenant_admin"

    members = await db_call(
        "GET", f"/api/v1/workspaces/{workspace_id}/members", headers=auth(token)
    )
    assert members.status_code == 200
    assert len(members.json()["data"]) == 2
    assert any(
        item["userId"] == member and item["roleName"] == "tenant_admin"
        for item in members.json()["data"]
    )

    removed = await db_call("DELETE", f"/api/v1/workspaces/{workspace_id}", headers=auth(token))
    assert removed.status_code == 204
