from __future__ import annotations

import hashlib
import hmac
from collections.abc import Sequence

SIGNATURE_PREFIX = "sha256="


def compute_signature(secret: str, *, timestamp: str, body: bytes) -> str:
    digest = hmac.new(
        secret.encode(),
        f"{timestamp}.".encode() + body,
        hashlib.sha256,
    ).hexdigest()
    return SIGNATURE_PREFIX + digest


def signature_is_valid(
    secrets: Sequence[str],
    *,
    timestamp: str,
    body: bytes,
    provided: str,
) -> bool:
    return any(
        hmac.compare_digest(compute_signature(secret, timestamp=timestamp, body=body), provided)
        for secret in secrets
    )
