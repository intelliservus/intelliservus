from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ...common.envelope import envelope

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, Any]:
    return envelope({"status": "ok"})
