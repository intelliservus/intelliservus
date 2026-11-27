# Tasks

> 实现语言：Python 3.12 + FastAPI（ADR-014）。行为验收标准与 `specs/tenant-identity/spec.md` 保持一致，不因语言切换而放宽。

## 1. 服务骨架与运行环境

- [x] 1.1 建立 `apps/saas-api`（Python 3.12 + FastAPI + uv），含 pydantic 配置校验、统一异常处理器（§12.1 信封 / §12.2 错误码）与 `GET /api/v1/healthz`；启动时校验必需配置（`DATABASE_URL`、JWT 密钥、Cookie 设置），缺失即退出；验证：`uv run pytest` 与 `uv run mypy` 通过，`GET /healthz` 返回 `{ data: { status: "ok" }, meta }`，删掉一个必填配置后进程启动失败并打印缺失项
- [x] 1.2 在 `docker-compose.yml` 增加平台 `postgres` 与 `saas-api`（独立 network 与卷、healthcheck、资源限制），`.env.example` 增补平台库与 JWT 配置；验证：`docker compose config` 通过，不带 profile 启动时 `web-console`/`postgres`/`saas-api` 全部 healthy，且平台网络与 `chatwoot-net` 无交集
- [x] 1.3 实现结构化日志与请求上下文：固定字段按 §13.2，入站沿用 `traceparent`（缺失则生成），响应返回 `X-Request-Id`；验证：单测断言日志字段齐全、入站 `traceparent` 被原样沿用、响应头存在，且日志中不出现密码/token/Cookie

## 2. 数据层与迁移

- [x] 2.1 实现薄 SQL 迁移执行器 `scripts/migrate.py`（按 `NNNN-<domain>-<desc>.sql` 顺序执行 + `schema_migrations` 版本表）与执行校验（库名与环境标记）；验证：在空库上执行迁移成功、版本表有记录，重复执行不产生变更，`DATABASE_URL` 指向非平台库时命令拒绝执行
- [x] 2.2 复用首版迁移 SQL：`iam`（users、roles、permissions、role_permissions、memberships、refresh_tokens）、`tenant`（tenants、workspaces）与 `audit.audit_logs`；按 §3.3 建唯一约束与索引；验证：迁移后表/约束存在，`(tenant_id, workspace_id, …)` 类唯一约束符合事实源，`audit_logs` 无 UPDATE/DELETE 权限
- [x] 2.3 建立薄 repository 与 `tenant_context(tenant_id)`：事务内 `SET LOCAL ROLE saas_app` + `set_config(..., true)`，repository 只接受外部传入的 `conn`；验证：单测断言事务提交/回滚后连接上 `app.tenant_id` 不可见，且类型层面无法在不传 `conn` 的情况下调用 repository

## 3. 认证

- [x] 3.1 实现 `POST /api/v1/auth/login`：Argon2id 校验、签发 access JWT（PyJWT）、写入 refresh Cookie；多租户成员未指定租户时返回 400 `PARAM_INVALID` 并列出候选；验证：集成测试覆盖成功登录、错误凭据、禁用用户、多租户选择四种情形，响应信封与 `openapi.yaml` 一致
- [x] 3.2 实现 `POST /auth/refresh`（轮换 + 复用检测）与 `POST /auth/logout`：旧 token 立即失效，复用已轮换 token 时吊销该家族全部 token；验证：集成测试断言正常刷新后旧 token 失效、复用旧 token 触发全量吊销并写 `decision = deny` 审计、登出后无法刷新
- [x] 3.3 实现 `GET /auth/me`：返回主体标识、显示名、`tenant_id`、`permissions`；权限点与后端授权判定同源；验证：集成测试断言返回的每个权限点都能实际通过对应端点、缺失的权限点对应端点返回 403
- [x] 3.4 收敛认证安全细节：`SameSite=Strict`（显式 `"Strict"` 大小写）+ `Secure` + `httpOnly` Cookie、`Origin` 白名单校验、401 错误码区分（`AUTH_TOKEN_MISSING`/`EXPIRED`/`INVALID`）、失败审计且不泄露用户是否存在；验证：安全用例覆盖跨 Origin 刷新、过期 token、篡改 token、错误凭据，全部返回预期错误码且审计存在

## 4. 租户、工作空间与成员

- [x] 4.1 实现租户与工作空间的 CRUD（`/api/v1/tenants`、`/api/v1/workspaces`），创建租户时在同一事务内创建首个工作空间并把创建者设为租户管理员；验证：集成测试断言创建后租户/工作空间/成员关系三者同时存在，失败时全部回滚
- [x] 4.2 实现成员与角色管理（`/api/v1/workspaces/{id}/members`）：添加、改角色、移除；移除后立即失去访问且其 refresh token 被吊销；验证：集成测试断言移除成员后同一 token 请求返回 403，且 `iam.refresh_tokens` 中该用户家族全部失效
- [x] 4.3 实现租户上下文解析：`scope=tenant` 从 token 取租户；`scope=platform` 从请求取目标租户并校验平台角色，所有跨租户操作写审计；平台角色的权限目录不得包含业务数据类型；验证：单测断言令牌与请求租户不一致时返回 `TENANT_SCOPE_MISMATCH`，平台超管跨租户请求必有审计记录，且平台角色访问业务数据类型端点返回 403、`/auth/me` 不含业务权限点

## 5. RBAC 与资源范围

- [x] 5.1 建立权限点目录与后端依赖守卫（FastAPI dependency），覆盖本变更全部管理端点；权限点命名与 `app/modules.ts` 的既有 permission 字符串对齐；验证：为每个端点生成一条「缺少权限点 → 403 `AUTH_FORBIDDEN`」用例并全部通过，且审计 `decision = deny`
- [x] 5.2 实现资源归属校验（tenant / workspace / 本人三级范围）；验证：跨租户与同租户跨工作空间的读写删用例全部拒绝，响应不含目标资源字段，且每个拒绝都有审计

## 6. 隔离测试与 RLS

- [x] 6.1 把现有 46 个行为测试移植为 pytest（`apps/saas-api/test/`），并建立 2 租户 × 每租户 2 工作空间的数据集，覆盖 AC-TEN-01 与 AC-TEN-02 的全部负向用例（读/写/删/导出）；验证：该套件在 CI 中执行并全部通过，且故意放宽一个租户条件时套件失败
- [x] 6.2 关闭 ADR-007：在真实连接池上验证事务级 `SET LOCAL`、连接归还后的可见性、并发请求下无串租户、平台超管旁路方案；验证：`docs/adr/ADR-007-*.md` 结论与 psycopg 3 连接池行为一致（必要时更新验证环境章节），事实源 §18 状态更新为已定
- [x] 6.3 落地 RLS：为 `iam`/`tenant`/`audit` 表启用行级策略，请求经 `tenant_context` 执行，平台超管旁路只对这三类表生效并强制审计；验证：绕过应用层直接执行 SQL 仍无法读到其他租户数据，超管旁路路径有对应审计，6.1 的隔离套件在 RLS 开启后仍全部通过，且用一个临时业务表证明新增表不会被平台旁路策略覆盖

## 7. 契约与 CI

- [x] 7.1 扩展 `packages/api-contracts/openapi.yaml`（auth 增量 + tenant/workspace/member 端点 + 新错误码）并重新生成类型；验证：`pnpm --filter @intelliservus/api-contracts generate` 后 `git diff --exit-code` 干净，`web-console` typecheck 通过，新增错误码已同步到事实源 §12.2
- [x] 7.2 CI 增加独立 Python 后端 job：`uv sync` → 迁移（Postgres service）→ `ruff check` → `mypy` → `pytest`，并保留契约生成 diff 检查；验证：PR 流水线包含后端步骤且全绿，故意让一个后端单测失败时流水线阻断

## Workflow follow-up

- 归档时把 `specs/tenant-identity` 增量合并进主规格，并回写事实源 §18（ADR-007、ADR-014）、§19 M1 勾选项、§20.9 完成记录。
- `web-console` 能力规格仍推迟到首个包含控制台业务页面的变更（0003 只让既有登录流对接真实后端）。
- ADR-006 的边界说明（平台会话 ≠ 客户凭证）在关闭 ADR-006 时并入其正文。
