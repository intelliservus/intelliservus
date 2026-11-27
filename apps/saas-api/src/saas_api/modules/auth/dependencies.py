from __future__ import annotations

from typing import cast

import jwt
from fastapi import Request

from ...common.dependencies import settings_of
from ...common.errors import AppError
from ...common.request_context import update_identity
from .principal import AuthenticatedUser, PrincipalScope


def require_principal(request: Request) -> AuthenticatedUser:
    settings = settings_of(request)
    authorization = request.headers.get("authorization")

    if not authorization or not authorization.startswith("Bearer "):
        raise AppError(401, "AUTH_TOKEN_MISSING", "missing bearer token")

    try:
        payload = jwt.decode(
            authorization[len("Bearer ") :],
            settings.jwt_secret,
            algorithms=["HS256"],
        )
    except jwt.ExpiredSignatureError:
        raise AppError(401, "AUTH_TOKEN_EXPIRED", "token expired") from None
    except jwt.InvalidTokenError:
        raise AppError(401, "AUTH_TOKEN_INVALID", "invalid token") from None

    principal = AuthenticatedUser(
        user_id=str(payload["sub"]),
        scope=cast(PrincipalScope, payload["scope"]),
        tenant_id=payload.get("tenant_id"),
        permissions=list(payload.get("permissions", [])),
        jti=str(payload.get("jti", "")),
    )
    update_identity(user_id=principal.user_id, tenant_id=principal.tenant_id)
    return principal
