from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

ACCESS_TTL_SECONDS = 900
REFRESH_TTL_DAYS = 30
REFRESH_TTL_SECONDS = REFRESH_TTL_DAYS * 24 * 60 * 60


@dataclass(frozen=True)
class IssuedRefreshToken:
    token: str
    token_hash: str
    family_id: str
    expires_at: datetime


def sha256_hex(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_refresh_token(family_id: str | None = None) -> IssuedRefreshToken:
    token = secrets.token_urlsafe(32)
    return IssuedRefreshToken(
        token=token,
        token_hash=sha256_hex(token),
        family_id=family_id or str(uuid.uuid4()),
        expires_at=datetime.now(UTC) + timedelta(days=REFRESH_TTL_DAYS),
    )
