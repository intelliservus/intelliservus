from __future__ import annotations

import re
from typing import Any

import pytest
from psycopg_pool import AsyncConnectionPool

from support import (
    ORIGIN,
    PASSWORD,
    Call,
    add_membership,
    auth,
    cookie_header,
    create_user,
    execute,
    fetch_all,
    insert_returning,
    login,
    token_of,
)

pytestmark = pytest.mark.usefixtures("clean_db")


async def seed(
    admin_pool: AsyncConnectionPool,
    password_hash: str,
    *,
    email: str = "user@poc.test",
    permissions: tuple[str, ...] = ("workspace:read",),
    tenant_count: int = 1,
    disabled: bool = False,
    platform_admin: bool = False,
) -> dict[str, Any]:
    user_id = await create_user(
        admin_pool,
        password_hash,
        email,
        platform_admin=platform_admin,
        disabled=disabled,
    )

    tenant_ids: list[str] = []
    for index in range(tenant_count):
        tenant_id = await insert_returning(
            admin_pool,
            "INSERT INTO tenant.tenants (name) VALUES (%s) RETURNING id",
            [f"Tenant {index}"],
        )
        workspace_id = await insert_returning(
            admin_pool,
            "INSERT INTO tenant.workspaces (tenant_id, name) VALUES (%s, %s) RETURNING id",
            [tenant_id, f"Workspace {index}"],
        )
        role_id = await insert_returning(
            admin_pool,
            "INSERT INTO iam.roles (tenant_id, name) VALUES (%s, 'tenant_admin') RETURNING id",
            [tenant_id],
        )
        for permission in permissions:
            await execute(
                admin_pool,
                """
                INSERT INTO iam.role_permissions (role_id, permission_key)
                VALUES (%s, %s) ON CONFLICT DO NOTHING
                """,
                [role_id, permission],
            )
        await add_membership(
            admin_pool,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=user_id,
            role_id=role_id,
        )
        tenant_ids.append(str(tenant_id))

    return {"user_id": user_id, "tenant_ids": tenant_ids}


async def test_login_returns_access_token_and_httponly_cookie(
    db_call: Call, admin_pool: AsyncConnectionPool, password_hash: str
) -> None:
    await seed(admin_pool, password_hash)

    response = await login(db_call, "user@poc.test")

    assert response.status_code == 200
    assert response.json()["data"]["access_token"]
    assert response.json()["data"]["expires_in"] == 900

    cookie = response.headers.get("set-cookie", "")
    assert "refresh_token=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=Strict" in cookie


async def test_wrong_password_and_unknown_user_share_the_same_error(
    db_call: Call, admin_pool: AsyncConnectionPool, password_hash: str
) -> None:
    await seed(admin_pool, password_hash)

    wrong = await login(db_call, "user@poc.test", "wrong-password")
    unknown = await login(db_call, "nobody@poc.test", "wrong-password")

    assert wrong.status_code == 401
    assert unknown.status_code == 401
    assert wrong.json()["error"]["code"] == "AUTH_TOKEN_INVALID"
    assert unknown.json()["error"]["code"] == wrong.json()["error"]["code"]
    assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]


async def test_disabled_user_cannot_login(
    db_call: Call, admin_pool: AsyncConnectionPool, password_hash: str
) -> None:
    await seed(admin_pool, password_hash, disabled=True)

    response = await login(db_call, "user@poc.test")

    assert response.status_code == 401


async def test_multi_tenant_user_without_tenant_id_gets_candidates(
    db_call: Call, admin_pool: AsyncConnectionPool, password_hash: str
) -> None:
    await seed(admin_pool, password_hash, tenant_count=2)

    response = await login(db_call, "user@poc.test")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PARAM_INVALID"
    assert len(response.json()["error"]["details"]["tenants"]) == 2


async def test_tenant_outside_membership_is_rejected(
    db_call: Call, admin_pool: AsyncConnectionPool, password_hash: str
) -> None:
    await seed(admin_pool, password_hash)

    response = await db_call(
        "POST",
        "/api/v1/auth/login",
        headers={"Origin": ORIGIN},
        json={
            "email": "user@poc.test",
            "password": PASSWORD,
            "tenant_id": "00000000-0000-0000-0000-000000000000",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "TENANT_SCOPE_MISMATCH"


async def test_refresh_rotates_and_reuse_revokes_family(
    db_call: Call, admin_pool: AsyncConnectionPool, password_hash: str
) -> None:
    seeded = await seed(admin_pool, password_hash)
    login_response = await login(db_call, "user@poc.test")
    old_cookie = cookie_header(login_response)

    refreshed = await db_call(
        "POST",
        "/api/v1/auth/refresh",
        headers={"Origin": ORIGIN, "Cookie": old_cookie},
    )
    assert refreshed.status_code == 200
    assert cookie_header(refreshed) != old_cookie

    reuse = await db_call(
        "POST",
        "/api/v1/auth/refresh",
        headers={"Origin": ORIGIN, "Cookie": old_cookie},
    )
    assert reuse.status_code == 401

    tokens = await fetch_all(
        admin_pool,
        "SELECT status FROM iam.refresh_tokens WHERE user_id = %s",
        [seeded["user_id"]],
    )
    assert tokens and all(row["status"] == "revoked" for row in tokens)

    audit = await fetch_all(
        admin_pool,
        "SELECT 1 FROM audit.audit_logs WHERE action = 'auth.refresh' AND decision = 'deny'",
    )
    assert len(audit) > 0


async def test_logout_prevents_further_refresh(
    db_call: Call, admin_pool: AsyncConnectionPool, password_hash: str
) -> None:
    await seed(admin_pool, password_hash)
    login_response = await login(db_call, "user@poc.test")
    cookie = cookie_header(login_response)

    logout = await db_call(
        "POST",
        "/api/v1/auth/logout",
        headers={"Origin": ORIGIN, "Cookie": cookie},
    )
    assert logout.status_code == 204

    refresh = await db_call(
        "POST",
        "/api/v1/auth/refresh",
        headers={"Origin": ORIGIN, "Cookie": cookie},
    )
    assert refresh.status_code == 401


async def test_refresh_without_or_with_foreign_origin_is_rejected(
    db_call: Call, admin_pool: AsyncConnectionPool, password_hash: str
) -> None:
    await seed(admin_pool, password_hash)
    login_response = await login(db_call, "user@poc.test")
    cookie = cookie_header(login_response)

    no_origin = await db_call("POST", "/api/v1/auth/refresh", headers={"Cookie": cookie})
    assert no_origin.status_code == 401

    bad_origin = await db_call(
        "POST",
        "/api/v1/auth/refresh",
        headers={"Origin": "http://evil.example", "Cookie": cookie},
    )
    assert bad_origin.status_code == 401


async def test_me_returns_principal_and_permissions(
    db_call: Call, admin_pool: AsyncConnectionPool, password_hash: str
) -> None:
    await seed(admin_pool, password_hash, permissions=("workspace:read", "tenant:read"))
    login_response = await login(db_call, "user@poc.test")
    token = token_of(login_response)

    me = await db_call("GET", "/api/v1/auth/me", headers=auth(token))
    assert me.status_code == 200
    assert me.json()["data"]["user"]["display_name"] == "Test User"
    assert me.json()["data"]["permissions"] == ["tenant:read", "workspace:read"]

    missing = await db_call("GET", "/api/v1/auth/me")
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "AUTH_TOKEN_MISSING"

    invalid = await db_call("GET", "/api/v1/auth/me", headers=auth("not-a-jwt"))
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "AUTH_TOKEN_INVALID"


async def test_platform_admin_only_gets_platform_permissions(
    db_call: Call, admin_pool: AsyncConnectionPool, password_hash: str
) -> None:
    await seed(
        admin_pool,
        password_hash,
        email="admin@poc.test",
        platform_admin=True,
        tenant_count=0,
    )

    response = await login(db_call, "admin@poc.test")
    assert response.status_code == 200

    me = await db_call("GET", "/api/v1/auth/me", headers=auth(token_of(response)))
    assert me.status_code == 200
    assert me.json()["data"]["scope"] == "platform"

    business = re.compile(r"^(conversation|message|knowledge|agent_run|tool_execution):")
    assert all(not business.match(item) for item in me.json()["data"]["permissions"])
