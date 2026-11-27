from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from psycopg_pool import AsyncConnectionPool

from ...common.config import Settings
from ...common.errors import AppError
from ...common.logging import JsonLogger
from ...database.transaction import tenant_context
from ..audit.service import AuditService
from ..iam.permissions import PLATFORM_PERMISSIONS
from ..iam.refresh_tokens_repository import RefreshTokenRecord, RefreshTokensRepository
from ..iam.users_repository import UserRecord, UsersRepository
from .dto import LoginRequest
from .password import hash_password, verify_password
from .principal import AuthenticatedUser
from .tokens import ACCESS_TTL_SECONDS, IssuedRefreshToken, new_refresh_token, sha256_hex

_dummy_hash: str | None = None


def _dummy_hash_value() -> str:
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("timing-equalizer-for-unknown-user")
    return _dummy_hash


@dataclass(frozen=True)
class AuthTokens:
    access_token: str
    refresh_token: str
    expires_in: int


@dataclass(frozen=True)
class ResolvedScope:
    tenant_id: str | None
    permissions: list[str]


class AuthService:
    def __init__(
        self,
        pool: AsyncConnectionPool,
        settings: Settings,
        logger: JsonLogger,
    ) -> None:
        self._pool = pool
        self._settings = settings
        self._audit = AuditService(pool, logger)

    async def login(self, body: LoginRequest, origin: str | None) -> AuthTokens:
        async with tenant_context(self._pool, None) as conn:
            user = await UsersRepository(conn).find_by_email(body.email)

        if user is None:
            # 与「密码错误」保持同一响应，并用一次哈希消耗抹平时序差异。
            verify_password(_dummy_hash_value(), body.password)
            await self._audit_deny(
                "auth.login",
                {"email": body.email, "reason": "unknown_user", "origin": origin},
                None,
            )
            raise AppError(401, "AUTH_TOKEN_INVALID", "invalid credentials")

        if user.status != "active" or not verify_password(user.password_hash, body.password):
            await self._audit_deny(
                "auth.login",
                {"userId": user.id, "reason": "bad_credentials", "origin": origin},
                user.id,
            )
            raise AppError(401, "AUTH_TOKEN_INVALID", "invalid credentials")

        requested = str(body.tenant_id) if body.tenant_id else None
        resolved = await self._resolve_scope(user, requested)
        issued = new_refresh_token()

        async with tenant_context(self._pool, resolved.tenant_id) as conn:
            await RefreshTokensRepository(conn).create(
                user_id=user.id,
                tenant_id=resolved.tenant_id,
                family_id=issued.family_id,
                token_hash=issued.token_hash,
                expires_at=issued.expires_at,
            )

        return AuthTokens(
            access_token=self._sign_access(user.id, resolved.tenant_id, resolved.permissions),
            refresh_token=issued.token,
            expires_in=ACCESS_TTL_SECONDS,
        )

    async def refresh(self, raw_token: str | None, origin: str | None) -> AuthTokens:
        await self._assert_origin(origin, "auth.refresh")
        if not raw_token:
            raise AppError(401, "AUTH_TOKEN_MISSING", "missing refresh token")

        kind = "invalid"
        reuse: RefreshTokenRecord | None = None
        user: UserRecord | None = None
        tenant_id: str | None = None
        permissions: list[str] = []
        issued: IssuedRefreshToken | None = None

        async with tenant_context(self._pool, None) as conn:
            repo = RefreshTokensRepository(conn)
            record = await repo.find_by_hash(sha256_hex(raw_token))
            if record is not None:
                if record.status != "active":
                    await repo.revoke_family(record.family_id)
                    kind = "reuse"
                    reuse = record
                elif record.expires_at <= datetime.now(UTC):
                    await repo.revoke_family(record.family_id)
                    kind = "expired"
                else:
                    users = UsersRepository(conn)
                    found = await users.find_by_id(record.user_id)
                    if found is None or found.status != "active":
                        kind = "invalid"
                    else:
                        user = found
                        tenant_id = record.tenant_id
                        permissions = (
                            list(PLATFORM_PERMISSIONS)
                            if found.is_platform_admin
                            else await users.permissions_for(found.id, record.tenant_id or "")
                        )
                        await repo.mark_rotated(record.id)
                        issued = new_refresh_token(record.family_id)
                        await repo.create(
                            user_id=found.id,
                            tenant_id=record.tenant_id,
                            family_id=issued.family_id,
                            token_hash=issued.token_hash,
                            expires_at=issued.expires_at,
                        )
                        kind = "ok"

        if kind == "reuse" and reuse is not None:
            await self._audit_deny(
                "auth.refresh",
                {
                    "userId": reuse.user_id,
                    "familyId": reuse.family_id,
                    "reason": "refresh_token_reuse",
                    "origin": origin,
                },
                reuse.user_id,
            )
            raise AppError(401, "AUTH_TOKEN_INVALID", "refresh token reuse detected")
        if kind == "expired":
            raise AppError(401, "AUTH_TOKEN_EXPIRED", "refresh token expired")
        if kind != "ok" or user is None or issued is None:
            raise AppError(401, "AUTH_TOKEN_INVALID", "invalid refresh token")

        return AuthTokens(
            access_token=self._sign_access(user.id, tenant_id, permissions),
            refresh_token=issued.token,
            expires_in=ACCESS_TTL_SECONDS,
        )

    async def logout(self, raw_token: str | None, origin: str | None) -> None:
        await self._assert_origin(origin, "auth.logout")
        if not raw_token:
            return

        async with tenant_context(self._pool, None) as conn:
            repo = RefreshTokensRepository(conn)
            record = await repo.find_by_hash(sha256_hex(raw_token))
            if record is not None:
                await repo.revoke_family(record.family_id)

    async def session(self, principal: AuthenticatedUser) -> dict[str, Any]:
        async with tenant_context(self._pool, principal.tenant_id) as conn:
            user = await UsersRepository(conn).find_by_id(principal.user_id)

        if user is None:
            raise AppError(401, "AUTH_TOKEN_INVALID", "user not found")

        return {
            "user": {"id": user.id, "display_name": user.display_name},
            "tenant_id": principal.tenant_id,
            "scope": principal.scope,
            "permissions": principal.permissions,
        }

    async def _resolve_scope(self, user: UserRecord, requested: str | None) -> ResolvedScope:
        if user.is_platform_admin:
            return ResolvedScope(tenant_id=None, permissions=list(PLATFORM_PERMISSIONS))

        async with tenant_context(self._pool, None) as conn:
            tenant_ids = await UsersRepository(conn).tenant_ids_for(user.id)

        if not tenant_ids:
            await self._audit_deny(
                "auth.login",
                {"userId": user.id, "reason": "no_membership"},
                user.id,
            )
            raise AppError(403, "AUTH_FORBIDDEN", "no tenant membership")

        if requested:
            if requested not in tenant_ids:
                await self._audit_deny(
                    "auth.login",
                    {
                        "userId": user.id,
                        "reason": "tenant_scope_mismatch",
                        "requestedTenantId": requested,
                    },
                    user.id,
                )
                raise AppError(403, "TENANT_SCOPE_MISMATCH", "requested tenant is not in scope")
            tenant_id = requested
        elif len(tenant_ids) > 1:
            raise AppError(
                400,
                "PARAM_INVALID",
                "tenant_id is required for multi-tenant users",
                {"tenants": tenant_ids},
            )
        else:
            tenant_id = tenant_ids[0]

        async with tenant_context(self._pool, tenant_id) as conn:
            permissions = await UsersRepository(conn).permissions_for(user.id, tenant_id)

        return ResolvedScope(tenant_id=tenant_id, permissions=permissions)

    def _sign_access(self, user_id: str, tenant_id: str | None, permissions: list[str]) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": user_id,
            "scope": "tenant" if tenant_id else "platform",
            "tenant_id": tenant_id,
            "permissions": permissions,
            "jti": str(uuid.uuid4()),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=ACCESS_TTL_SECONDS)).timestamp()),
        }
        return jwt.encode(payload, self._settings.jwt_secret, algorithm="HS256")

    async def _assert_origin(self, origin: str | None, action: str) -> None:
        if not origin or origin not in self._settings.allowed_origins:
            await self._audit_deny(
                action,
                {"reason": "origin_rejected", "origin": origin},
                None,
            )
            raise AppError(401, "AUTH_TOKEN_INVALID", "origin not allowed")

    async def _audit_deny(
        self,
        action: str,
        details: dict[str, Any],
        actor_id: str | None,
    ) -> None:
        await self._audit.record(
            actor_type="user" if actor_id else "system",
            actor_id=actor_id,
            action=action,
            resource_type="auth",
            decision="deny",
            details=details,
        )
