from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PrincipalScope = Literal["tenant", "platform"]


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    scope: PrincipalScope
    tenant_id: str | None
    permissions: list[str]
    jti: str
