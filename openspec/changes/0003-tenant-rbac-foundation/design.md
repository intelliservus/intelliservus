# Design

## Context

- 事实源：`docs/项目开发文档.md`。本变更受 §1.3（角色）、§3.2（`iam`/`tenant` schema）、§6.1–§6.2（授权链与隔离）、§12.1–§12.2（契约与错误码）、§15.2（Compose）、§16.2（AC-TEN）约束。
- `apps/web-console` 已按 `packages/api-contracts/openapi.yaml` 实现登录/刷新/登出与权限守卫，后端不存在；本变更必须让既有契约变成真，而不是改前端去适配新契约。
- `0002` 把迁移框架显式移交给本变更；M0 工作项 5 把结构化日志与最小 Trace 移交给「首个承载服务」。
- 本变更的后端实现经历一次语言切换：首版按 NestJS 11 落地，后改为 Python 3.12 + FastAPI（ADR-014）。行为规格、验收标准与迁移 SQL 均不变。
- ADR-007（RLS 与连接池上下文）未关闭；ADR-006（客户凭证）与本变更无关，但两者边界必须写清。
- `docs/` 与 `spikes/` 本地化，不入 git；本变更的结论以 `openspec/specs/` 与 `docs/adr/`（本机）为准。

## Goals / Non-Goals

**Goals:**

- 一个可启动、可迁移、可测试的 `saas-api`，成为后续所有后端变更的宿主。
- 让控制台现有登录流在真实后端下工作，且不修改前端契约。
- 用测试证明 AC-TEN-01/02：跨租户、跨工作空间的读/写全部被拒绝。
- 在变更内关闭 ADR-007，并交付 RLS 作为第二道防线。

**Non-Goals:**

- 不做控制台管理页面、不做客户身份、不做 Chatwoot 开通编排。
- 不引入 ORM、Redis、消息队列。
- 不做 MFA/SSO/密码找回（P2 或后续变更）。
- 不做完整 OpenTelemetry 后端接入；只保证 traceparent 传播与结构化日志字段。

## Decisions

### D1 服务形态：`apps/saas-api`，Python 3.12 + FastAPI 模块化单体

```text
apps/saas-api/
  src/saas_api/
    main.py                  bootstrap + 配置校验 + 异常处理器
    common/                  信封、错误码、日志、trace、请求上下文
    modules/auth/            登录 / 刷新 / 登出 / me
    modules/iam/             users, roles, permissions, memberships, refresh tokens
    modules/tenant/          tenants, workspaces, members
    modules/audit/           audit_logs 写入
    database/                连接池、事务、迁移入口
  migrations/                纯 SQL（NNNN-<domain>-<desc>.sql）
  scripts/migrate.py         薄迁移执行器
  tests/                     pytest
```

- 模块之间只通过 service 函数/类调用，**禁止跨模块直接写表**（§3.2）。每个模块的 repository 只操作自己 schema 的表。
- pydantic 模型做边界校验（`extra="forbid"` 对齐原 `forbidNonWhitelisted`）；统一异常处理器输出 §12.1 的信封与 §12.2 的错误码。
- 启动时校验必需配置（数据库 URL、JWT 密钥、Cookie 域/同源策略），缺失即退出（§15.3）。
- 框架与语言选择见 `docs/adr/ADR-014-backend-framework.md`。

### D2 数据访问：`psycopg 3` + 薄 SQL 迁移执行器 + 薄 repository

| 候选 | 结论 | 理由 |
|---|---|---|
| **`psycopg 3`（async）+ 薄 SQL 执行器 + 薄 repository（选用）** | 采纳 | 迁移是纯 SQL，事务边界可见；RLS 的 `SET LOCAL` 能放在显式事务里；不隐藏连接池行为；与原 3 个迁移文件零改动兼容 |
| SQLAlchemy / ORM | 否决 | 客户端抽象会遮住事务与会话变量；schema 与「模块不得跨 schema 写表」张力大 |
| Alembic | 否决 | 迁移需改写为 Python 脚本或 `op.execute` 包装，破坏纯 SQL；版本表语义与现有 `schema_migrations` 不同 |
| asyncpg | 备选 | 性能更好，但 `SET LOCAL ROLE` 与连接选项的用法不如 psycopg 直观；控制面 QPS 不是瓶颈 |

约定：

- 迁移文件按 `NNNN-<domain>-<desc>.sql` 命名，只前进；破坏性变更分两步（§15.5）。
- `database/transaction.py` 提供 `tenant_context(tenant_id)`：`BEGIN` → `SET LOCAL ROLE saas_app` → `set_config('app.tenant_id', …, true)` → 业务 → `COMMIT/ROLLBACK`。
- 所有 repository 函数必须接收 `conn`（事务句柄），不允许在 repository 内部自行取连接。
- 迁移由显式命令执行（`uv run python scripts/migrate.py`），不在容器启动时自动跑。

### D3 会话与令牌

| 项 | 决策 |
|---|---|
| Access token | JWT（HS256，PyJWT），15 分钟，仅存内存（前端已如此） |
| Refresh token | 32 字节随机值，`httpOnly; Secure; SameSite=Strict` Cookie，30 天 |
| 服务端存储 | `iam.refresh_tokens` 存 SHA-256 哈希 + 家族 id + 状态 + 过期时间 |
| 轮换 | 每次刷新签发新 token 并把旧 token 标记为 `rotated` |
| 复用检测 | 已 `rotated`/`revoked` 的 token 再次出现 → 吊销该家族全部 token + 审计 |
| 登出 | 吊销当前 token 家族，清除 Cookie |
| 密码哈希 | Argon2id（`argon2-cffi`，m=19456,t=2,p=1；已验证与 Node 生成的哈希双向兼容） |

Access token claims：

```json
{
  "sub": "user_uuid",
  "scope": "tenant | platform",
  "tenant_id": "uuid | null",
  "roles": ["tenant_admin"],
  "permissions": ["workspace:read", "..."],
  "iat": 0,
  "exp": 0,
  "jti": "uuid"
}
```

上例为租户用户令牌；平台超管令牌的 `roles` 为 `["platform_admin"]`，`permissions` 只含平台级权限点，不含任何业务数据类型。

- 普通用户 `scope = tenant`，`tenant_id` 必填；一个用户属于多个租户时，登录必须显式选择（未提供则返回 400 `PARAM_INVALID`，`details.tenants` 列出候选）。
- 平台超管 `scope = platform`，`tenant_id` 为空；跨租户请求必须携带目标 `tenant_id`，并按 §1.3 全部审计。
- **平台角色的权限边界（收窄）**：`platform_admin` 的权限点只覆盖租户、工作空间与全局配置（如 `tenant:manage`、`workspace:read`、`audit:read`），**不得包含任何业务数据类型**（`conversation:*`、`message:*`、`knowledge:*`、`agent_run:*`、`tool_execution:*`）。
- 跨租户读取租户业务数据一律拒绝（403 `AUTH_FORBIDDEN`），即使调用者是平台超管。排障需要读取业务数据时，只能走后续的显式扮演机制（`POST /auth/impersonate` + `act` 声明 + 时限 + 理由 + 租户可见审计），该机制不在本变更内实现。
- 理由：权限放宽可以随时做，收紧要付迁移成本；而 0003 尚未引入任何业务表，现在收窄的成本为零。

### D4 平台会话与 ADR-006 的边界

§6.4 的 JWS/ES256 是**客户身份凭证**（`customer_id` + `scope` + `auth_level`），由企业身份服务签发，用于工具授权；本变更的 JWT 是**平台用户会话**。

两者不得混用：平台会话 token 不得作为客户身份凭证传给 Tool Executor，客户凭证也不得用于管理 API。该边界写入 `docs/adr/ADR-006` 的前置说明，本变更只实现前者。

### D5 租户上下文与授权链

```text
access token
  → 校验签名/过期/jti 未吊销
  → 解析 scope
      ├─ tenant   → tenant_id 固定，成员关系必须存在
      └─ platform → 目标 tenant_id 来自请求，必须有平台角色，写审计
  → 校验 workspace 成员关系（workspace 级资源）
  → 校验 RBAC 权限点
  → 校验资源 tenant_id / workspace_id 归属
  → 执行
```

- 请求里的 `tenant_id`/`workspace_id` 只用于定位；与 token 推导不一致时返回 `TENANT_SCOPE_MISMATCH`（403）。
- 所有拒绝（401/403）写 `audit_logs`，`decision = deny`，不含密码与 token。

### D6 RLS：先应用层，后纵深防御

本变更内的顺序固定：

1. 应用层：所有查询经 repository 强制注入 `tenant_id` 条件；隔离负向测试先通过。
2. 关闭 ADR-007：在真实连接池上验证 `SET LOCAL app.tenant_id` 的事务级语义、连接归还前后的行为、平台超管旁路方式。
3. RLS：对 `iam` / `tenant` / `audit` 表启用 `USING (tenant_id = current_setting('app.tenant_id')::uuid)`；平台超管的旁路策略**只对这三类表生效**。
4. 业务表（后续变更引入的 `support` / `knowledge` / `agent` / `tooling` 等）**不得继承**平台旁路。本变更不为业务表预留任何「平台可读」策略；新增业务表时必须按租户策略编写，是否需要扮演访问由后续变更决定。
5. 应用连接必须在事务内切换到非超级用户角色（`saas_app`）：超级用户始终绕过 RLS，`FORCE ROW LEVEL SECURITY` 也无效（实测）。完整结论见 `docs/adr/ADR-007-rls-and-pool-context.md`。

禁止使用会话级 `SET`（连接池会串租户）。若 ADR-007 的 PoC 发现无法满足，则 RLS 任务改为记录结论并顺延，不阻塞前两组。

### D7 契约：以既有 OpenAPI 为准

- `/api/v1/auth/{login,refresh,logout,me}` 的响应形状、Cookie 语义与错误码以 `packages/api-contracts/openapi.yaml` 现值为准；本变更只做增量（租户/工作空间/成员端点）。
- 新增错误码必须同时更新事实源 §12.2 与 OpenAPI；`web-console` 的 `errors.ts` 映射需要同步（不在本变更内改，但要在 tasks 中标注为跨仓一致性检查）。
- Cookie 的 `SameSite=Strict` 依赖同源部署（ADR-013 D5），本变更不改部署形态。

### D8 日志与 Trace

- 结构化 JSON 日志，字段与 §13.2 一致：`ts, level, service, trace_id, span_id, tenant_id, workspace_id, user_id, code, msg, duration_ms`。
- 入站读取 `traceparent`，缺失则生成；响应返回 `X-Request-Id`。
- 禁止记录：密码、token、Cookie、完整请求体。
- 完整 OpenTelemetry 导出留到 `observability` 能力落地；本变更只保证上下文传播。

### D9 本地与 CI

- Compose 增加平台 `postgres`（独立 network/卷/healthcheck），与 `chatwoot-net` 隔离；`saas-api` 加入同一平台网络，`web-console` 的 nginx 反代指向它。
- `apps/saas-api` 退出 pnpm workspace：根 `pnpm lint/typecheck/test/build` 不再覆盖它，后端由 `uv` 管理。
- CI 增加独立 Python job：`uv sync` → 迁移（Postgres service 容器）→ `ruff check` → `mypy` → `pytest`；契约生成 diff 检查保留在 Node job。
- 测试数据库使用真实 PostgreSQL（CI service 容器 / 本地 Compose），不使用内存数据库替代。
- 容器基础镜像 `python:3.12-slim`（Debian）：`psycopg[binary]` 与 `argon2-cffi` 的 wheel 最可靠，避免 Alpine/musl 编译。

## Risks / Trade-offs

| 风险 | 缓解 |
|---|---|
| 范围超 20 条任务（§20.4） | 任务表按 7 组压到 20 条；控制台页面与 Chatwoot 编排明确出界 |
| RLS 与连接池串租户 | 只用事务级 `SET LOCAL`；ADR-007 PoC 用并发请求验证连接归还后不可见 |
| 平台超管绕过 RLS 成为漏洞 | 旁路仅覆盖 `iam`/`tenant`/`audit`；业务权限点禁止下放给平台角色；4.3 与 6.3 各有一条负向验收 |
| 平台角色被顺手扩权 | 权限点目录按资源类型分组，业务类型与平台类型分列；spec 明确禁止平台角色持有业务权限；`/auth/me` 负向断言 |
| 前端契约被后端「顺手改」 | 以 `openapi.yaml` 现值为输入；改动必须先在契约里体现并跑 diff 检查 |
| 多租户成员关系导致登录歧义 | V1 一个会话一个租户；多租户用户登录时必须选择，不提供静默回退 |
| `argon2-cffi` / `psycopg` 在 Alpine 上缺 wheel | 使用 `python:3.12-slim`（Debian），镜像不装编译工具链 |
| FastAPI/pydantic 校验语义与 class-validator 不一致 | `EmailStr` 拒绝 `.test` 保留域，需自定义邮箱校验器；Starlette 原样输出 `SameSite` 值，必须显式传 `"Strict"`；46 个行为测试作为回归门 |
| `saas-api` 退出 pnpm workspace 后根脚本不再覆盖 | CI 增加独立 Python job；根 `package.json` 脚本注明覆盖范围 |
| OpenAPI 仍为手写，FastAPI 自动生成能力暂未使用 | 本次保持契约优先、控制台零改动；代码优先留到独立变更 |
| 迁移在错误库上执行 | 迁移命令校验 `DATABASE_URL` 中的库名与环境标记，CI 与本地显式区分 |

## Migration Plan

- 新增平台库与 schema，无存量数据迁移。
- 落地顺序：服务骨架 → 库与迁移 → 认证 → 租户/成员 → RBAC/范围 → 隔离测试 → ADR-007 + RLS → 契约与 CI。
- 回滚：删除 `apps/saas-api` 与平台库卷即可；`web-console` 在 `saas-api` 缺席时仍能启动（nginx resolver 已处理），但登录返回 502。
- 归档前必须关闭 ADR-007 并回写事实源 §18/§19/§20.9。

## Open Questions

- 租户切换是否需要独立端点（`POST /auth/switch-tenant`），还是 V1 只支持重新登录？不影响任务拆分。
- 平台超管的 RLS 旁路用数据库角色还是策略表达式？由 ADR-007 的 PoC 结论决定。
- 密码复杂度与锁定策略的具体数值：V1 先用最小长度 + 失败计数，细节在 `0004` 前后补齐。
