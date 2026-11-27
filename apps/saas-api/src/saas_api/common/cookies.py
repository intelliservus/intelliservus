from __future__ import annotations

from urllib.parse import unquote


def read_cookie(header: str | None, name: str) -> str | None:
    if not header:
        return None
    for part in header.split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return unquote(value)
    return None
