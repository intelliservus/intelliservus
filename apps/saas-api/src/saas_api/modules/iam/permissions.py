from __future__ import annotations

"""权限点目录。新增权限点必须同步事实源 §12.2 与 `iam.permissions` 迁移。"""

PLATFORM_PERMISSIONS: tuple[str, ...] = (
    "overview:read",
    "tenant:read",
    "tenant:manage",
    "workspace:read",
    "workspace:manage",
    "audit:read",
)

TENANT_ADMIN_PERMISSIONS: tuple[str, ...] = (
    "overview:read",
    "tenant:read",
    "tenant:manage",
    "workspace:read",
    "workspace:manage",
    "member:manage",
    "audit:read",
)

AGENT_PERMISSIONS: tuple[str, ...] = (
    "overview:read",
    "tenant:read",
    "workspace:read",
)
