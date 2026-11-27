from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from ...common.cookies import read_cookie
from ...common.dependencies import logger_of, pool_of, settings_of
from ...common.envelope import envelope
from .dependencies import require_principal
from .dto import LoginRequest
from .principal import AuthenticatedUser
from .service import AuthService
from .tokens import REFRESH_TTL_SECONDS

router = APIRouter()

REFRESH_COOKIE = "refresh_token"
COOKIE_PATH = "/api/v1/auth"


def _service(request: Request) -> AuthService:
    return AuthService(pool_of(request), settings_of(request), logger_of(request))


def _set_refresh_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=REFRESH_TTL_SECONDS,
        path=COOKIE_PATH,
        httponly=True,
        secure=settings_of(request).cookie_secure,
        samesite="Strict",  # type: ignore[arg-type]  # 契约断言大小写敏感的 SameSite=Strict
    )


@router.post("/auth/login")
async def login(body: LoginRequest, request: Request) -> JSONResponse:
    tokens = await _service(request).login(body, request.headers.get("origin"))
    response = JSONResponse(
        content=envelope(
            {"access_token": tokens.access_token, "expires_in": tokens.expires_in}
        )
    )
    _set_refresh_cookie(response, request, tokens.refresh_token)
    return response


@router.post("/auth/refresh")
async def refresh(request: Request) -> JSONResponse:
    raw = read_cookie(request.headers.get("cookie"), REFRESH_COOKIE)
    tokens = await _service(request).refresh(raw, request.headers.get("origin"))
    response = JSONResponse(
        content=envelope(
            {"access_token": tokens.access_token, "expires_in": tokens.expires_in}
        )
    )
    _set_refresh_cookie(response, request, tokens.refresh_token)
    return response


@router.post("/auth/logout")
async def logout(request: Request) -> Response:
    raw = read_cookie(request.headers.get("cookie"), REFRESH_COOKIE)
    await _service(request).logout(raw, request.headers.get("origin"))
    response = Response(status_code=204)
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
    return response


@router.get("/auth/me")
async def me(
    request: Request,
    principal: Annotated[AuthenticatedUser, Depends(require_principal)],
) -> dict[str, Any]:
    return envelope(await _service(request).session(principal))
