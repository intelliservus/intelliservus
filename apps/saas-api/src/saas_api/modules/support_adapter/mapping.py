from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from psycopg import AsyncConnection


@dataclass(frozen=True)
class ChannelMapping:
    tenant_id: str
    workspace_id: str
    channel_id: str | None


@dataclass(frozen=True)
class Unresolved:
    reason: str


MappingResult = ChannelMapping | Unresolved


class MappingResolver(Protocol):
    """Workspace/channel 解析端口。`0005` 用映射表实现，`0004` 只有未解析实现。"""

    async def resolve(
        self,
        conn: AsyncConnection[object],
        *,
        provider: str,
        account_id: str,
        inbox_id: str | None,
    ) -> MappingResult: ...


class UnmappedResolver:
    """`0004` 的唯一实现：映射表尚不存在，所有事件都停在 `pending_mapping`。"""

    async def resolve(
        self,
        conn: AsyncConnection[object],
        *,
        provider: str,
        account_id: str,
        inbox_id: str | None,
    ) -> MappingResult:
        return Unresolved("mapping tables not available until 0005")
