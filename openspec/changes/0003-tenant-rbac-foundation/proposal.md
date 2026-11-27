# Proposal

## Why

M0 已退出：Chatwoot 接入已按 ADR-001~004 落地验证，控制台的认证流程却仍对着一个无人实现的契约运行（`openapi.yaml` 里已有 `/auth/*`，后端不存在，E2E 全靠 `page.route`）。与此同时，事实源 §3.2 的 `iam` / `tenant` schema、§6.1 的授权链、§16.2 的 AC-TEN-01/02/03 都还没有任何实现，`0002` 显式移交给本变更的迁移框架也仍是空白。M1 的其余三个变更（`0004`–`0006`）全部依赖租户模型与 RBAC 才能写代码。

## What Changes

- 建立 `apps/saas-api`（Python 3.12 + FastAPI 模块化单体）：配置校验、`/healthz`、结构化日志、W3C traceparent 传播。
- 建立平台 PostgreSQL 与迁移框架（薄 SQL 执行器 + `psycopg 3` + 薄 repository 层），首版迁移覆盖 `iam` / `tenant` schema 与 refresh token 表。
- 实现平台会话认证：`POST /auth/login`、`POST /auth/refresh`（轮换 + 复用检测）、`POST /auth/logout`、`GET /auth/me`，与 `packages/api-contracts/openapi.yaml` 的信封和错误码一致。
- 实现租户、工作空间、成员的 CRUD 与角色管理。
- 实现授权链：token 推导租户上下文 → 成员关系 → RBAC 权限点 → 资源归属，拒绝写审计。
- 落地数据隔离：应用层强制租户条件 + 隔离负向测试（AC-TEN-01/02/03）；在变更内关闭 ADR-007，随后加 PostgreSQL RLS 作为纵深防御。
- CI 增加独立 Python 后端 job（`uv sync` → 迁移 → lint → typecheck → test）与契约生成校验。

## Capabilities

### New Capabilities

- `tenant-identity`：平台会话认证、租户与工作空间生命周期、成员与角色、RBAC 与资源范围、租户数据隔离。

### Modified Capabilities

- 无。

## Impact

- **代码**：新增 `apps/saas-api`（Python + uv）；`docker-compose.yml` 增加平台 PostgreSQL；`apps/saas-api` 退出 pnpm workspace，根 `pnpm` 脚本不再覆盖它。
- **接口**：`/api/v1/auth/*` 从契约变为实现；新增 `/api/v1/tenants`、`/api/v1/workspaces`、`/api/v1/workspaces/{id}/members`。`packages/api-contracts/openapi.yaml` 随之扩展。
- **数据**：新平台库与 `iam` / `tenant` schema；不触碰 Chatwoot 库。
- **部署**：`saas-api` 加入 Compose 与 nginx 反代（`web-console` 已就位），健康检查与资源限制按 §15.2。
- **文档**：关闭 ADR-007、新增 ADR-014（后端框架与语言，`docs/adr/`）；更新事实源 §2.2 / §2.4 / §12.4 / §18 状态、§19 M1 勾选项、§20.9 完成记录。
- **前置依赖**：`0001`（已归档，ADR-001~004）与 `0002`（已归档）。本变更不依赖 ADR-005（Runtime 通信）与 ADR-006（客户身份凭证）。

## Out of Scope

- **不实现控制台业务页面**：本变更只让既有登录流对接真实后端；租户/工作空间/成员的管理界面留到首个包含这些页面的变更，`web-console` 能力规格同时推迟（延续 `0002` 的 follow-up 约定）。
- **不实现客户身份（T0–T3）与客户凭证 JWS**：属 §6.4 与 ADR-006 的范围，M3 交付。本变更的平台会话与该体系无关，边界写入 `design.md`。
- **不实现 Chatwoot Account 开通编排**：ADR-012 已有结论，但编排属于 `0005-channel-mapping`。
- **不引入 Redis**：队列通知、限流缓存留到真正需要的变更。
- **不做 MFA、SSO、密码策略高级项**：事实源列为 P2。
