# Design

## Context

见 `proposal.md`。影响实现方式的现状：

- `0003` 已交付 `saas-api` 骨架、纯 SQL 迁移执行器、`tenant_context`（`SET LOCAL ROLE saas_app` + `app.scope` / `app.tenant_id`）与 RLS 策略；策略只认 `app.scope = 'platform'` 或匹配的 `app.tenant_id`。
- `RequestContextMiddleware` 只注入 trace/request-id 与写访问日志，**不缓冲请求体**，所以路由层可以拿到原始字节。
- 上游事实已由 ADR-001/002/003/004 锁定：`v4.20.1-ce`、`X-Chatwoot-Delivery` 恒存在、`sha256=HMAC(secret, "{ts}.{raw}")`、outbox + `SKIP LOCKED`。
- `0005`（映射表）与 `0007`（Coordinator）尚未实现，因此本变更必须在"没有映射、没有下游消费者"的前提下可独立验收。

## Goals / Non-Goals

**Goals:**

- 验签失败、越界、重复投递三类输入的行为可被单测与集成测试逐条断言（AC-MSG-01）。
- Ingress 的数据库权限低于控制面：即使端点被攻破，也读不到任何租户业务数据。
- 事件标准化后的字段与 `0001` 采样的真实 payload 一一对应，且可在 CI 中回放。
- `0005` / `0007` 接入时不需要改本变更的表结构与事件契约。

**Non-Goals:**

- 不解决"事件属于哪个租户"——解析端口留给 `0005`，本变更只保证未解析事件不丢、不误归属。
- 不做投递顺序保证与合并窗口——`§5.6`/`§5.5` 的串行化依赖 Coordinator（`0007`）。
- 不做任何出站请求，因此不产生 Outbound Security 依赖。

## Decisions

### D1. Ingress 路径与契约边界

端点定为 `POST /api/v1/ingress/chatwoot`，独立于控制台前缀的鉴权体系（不经 `Authorization`，只凭签名）。

- 备选 `/internal/v1/...`：否决。`§12.4` 的 internal 前缀约定为服务间调用，鉴权模型不同。
- 备选加入 `openapi.yaml`：否决。该契约由 `web-console` 消费并生成 TS 类型，上游 webhook 契约与之无关；改为在 `docs/` 之外用测试 fixture 固化字段。

### D2. 验签顺序与原始体

路由内先 `raw = await request.body()`，按 ADR-003 的固定顺序执行：`Content-Type` 形状 → `len(raw) <= 1MB` → `|now - ts| <= 300s` → `hmac.compare_digest` → 投递去重。

- 备选依赖注入/中间件读取 body：否决。中间件缓冲会放大内存占用，且解析顺序容易在重构中被颠倒。
- 签名比较必须常数时间；时间窗判断使用 `X-Chatwoot-Timestamp`（Unix 秒），缺失即视为非法。
- 失败语义：非 JSON/超限 `413`，签名或时间戳失败 `401`，重复投递 `200` 且体为空信封。错误响应不得回显期望签名或 secret 片段。

### D3. 投递幂等键与降级策略

唯一键 `(provider, account_id, delivery_key)`；`delivery_key` 取 `X-Chatwoot-Delivery`。

- Header 缺失时：创建型事件（`message_created` / `contact_created` / `conversation_created`）使用 `§5.4` 复合键并置 `degraded = true`；非创建型事件改用随机键 + `degraded = true`，靠业务层幂等吸收重复。
- 备选对非创建型也套复合键：否决。ADR-003 已实测该类事件缺少 message id，会误判为重复而丢事件。
- 接收事务严格按 `§5.2` 顺序：`webhook_deliveries` → `support_events` → `outbox_events`，同一事务提交后返回 2xx；任何一步失败返回 5xx 让上游重投。

### D4. Ingress 的数据库权限隔离

新增角色 `saas_ingress`（`NOLOGIN`），只授予 `integration.webhook_deliveries`、`support.support_events`、`integration.outbox_events` 三张表的 `INSERT`；不授予任何 `SELECT` 业务表权限。接收事务用 `app.scope = 'ingress'`，现有 RLS 策略因不匹配 `platform` 与 `tenant_id` 而全部拒绝。

- 备选复用 `tenant_context(None)`（即 `app.scope='platform'`）：否决。该 scope 可读全部租户数据，公开端点上不可接受。
- Worker 才使用 `saas_app` + 平台 scope 领取 outbox，解析出 `tenant_id` 后再切到 `SET LOCAL` 租户 scope 写业务表。

### D5. 映射解析端口与 `pending_mapping`

`support_adapter` 定义 `MappingResolver` 端口：输入 `(provider, account_id, inbox_id)`，输出 `Resolved(tenant_id, workspace_id, channel_id)` 或 `Unresolved`。`0004` 的唯一实现恒返回 `Unresolved`。

- 未解析事件：`support_events.status = 'pending_mapping'`，`tenant_id` / `workspace_id` 允许为 `NULL`，Worker 不重试、不投递下游。
- `0005` 交付映射表后替换实现并增加回填任务；`0004` 不预留任何"从 payload 猜租户"的分支。
- 备选在 `0004` 建映射表：否决。跨能力建表违反 `§20.4`，且会让 `0005` 失去可独立验收的主体。

### D6. 表归属切分

| 表 | 本变更 | 后续 |
|---|---|---|
| `integration.webhook_deliveries` | 建表 + 唯一约束 | — |
| `integration.outbox_events` | 建表 + `(status, available_at)` 索引 | — |
| `integration.message_processing_records` | 建表 + `(message_id, processing_type)` 唯一 | — |
| `support.support_events` | 建表 + `delivery_id` 索引 | 回填由 `0005` 驱动 |
| `support.conversations` / `support.messages` | 最小字段集（外部 ID、方向、时间、原始摘要引用） | `state_version` / `ai_status` / `handoff_status` 由 `0007` 增列 |
| `support.chatwoot_mappings` / `support.channels` | 不建 | `0005` |

`support_events.payload` 只存顶层字段与事件类型的白名单子集，不存整包（`0001` 结论 #11）。

### D7. Worker 形态

新增独立入口与 Compose 单元 `saas-worker`（同一镜像，不同 command），不复用 `saas-api` 进程内的后台任务。

- 理由：队列消费需要独立扩缩、独立重启与独立超时；`0008` / `0017` 还会挂载其它任务域。
- 领取 SQL 采用 `§12.4` 的 `FOR UPDATE SKIP LOCKED` 单条领取；空闲时指数退避轮询（上限 5s），不引入 Redis 唤醒。
- 退避：2s/4s/8s/16s/32s，抖动 ±20%，`max_attempts = 5` 后置 `dead_letter` 并保留完整信封；重试写回 `trace_id`、`attempt`、`retry_of`。
- 消费幂等：`INSERT INTO message_processing_records ... ON CONFLICT DO NOTHING`，冲突即 `skipped_duplicate`，不重复创建下游任务。

### D8. Webhook secret 的存储与轮换

`0004` 使用进程级 `CHATWOOT_WEBHOOK_SECRETS`（逗号分隔，支持双 secret 过渡窗口）。读取后只在内存中参与 HMAC，不写日志、不进错误响应。

- 升级路径（`0005` 引入 per-account secret 时执行）：新增 `integration.webhook_secrets`，`ciphertext` 由 AES-GCM 加密，主密钥来自 `SECRET_ENCRYPTION_KEY`；验签时按 `account_id` 取密文解密，env 值降级为兜底。
- 本变更**不建**该表，只在 design 与任务里留出升级点，避免 `0005` 二次迁移。

### D9. 合约测试基线

把 `spikes/chatwoot-poc/findings/samples` 中覆盖 `message_created` / `message_updated` / `conversation_*` / `contact_*` / `agent_bot` / `private` 的样本脱敏后固化到 `apps/saas-api/tests/contract/fixtures/chatwoot-4.20.1/`，每条带来源与采集日期元数据。

- 回放方式：测试重算签名并直接调用 ASGI app，断言产生的事件类型、过滤结果与字段映射；不需要真实 Chatwoot 实例。
- 真实实例校验作为本地/手动步骤（Compose `chatwoot` profile），不进 CI：启动成本与 flaky 风险不可接受。
- `spikes/chatwoot-poc/` 在 fixture 固化完成后删除（`0001` design 的约定），不保留为可执行代码。

### D10. AC-MSG-02 的边界

本变更只保证排序字段（`provider_created_at` / `provider_message_id`）与业务幂等键就位，并交付 `message_processing_records` 的骨架。合并窗口、迟到判定、会话串行化与"不为迟到消息单独回复"由 `0007` 实现并关闭 AC-MSG-02。

## Risks / Trade-offs

- [`support_events.tenant_id` 可空削弱 RLS 语义] → Ingress 角色无业务表读权限，且未解析事件不进任何租户查询路径；`0005` 落地后增加"回填完成率"监控并收紧约束。
- [1MB 上限可能拒绝真实的长会话 payload] → 超限返回 `413` 并计数；上线后按实际分布调整阈值，调整前先记录最大观测体量。
- [env 单 secret 无法支持多租户轮换] → 双 secret 过渡窗口 + `0005` 的加密存储升级路径；轮换不要求停机。
- [轮询 Worker 在低延迟要求下不理想] → ADR-004 已确认 outbox 为事实源，Redis 唤醒留到压测暴露问题；接口上先把"唤醒"抽成空实现，避免以后改领取协议。
- [合约 fixture 与上游版本漂移] → fixture 目录带版本号；升级 Chatwoot 时按 `§15.5` 重新采集，测试失败即停止升级。
- [Ingress 与 Worker 同镜像不同 command，配置错误可能双跑] → Compose 分别声明健康检查与资源限制，Worker 启动时校验不含 `PORT` 绑定。

## Migration Plan

1. 迁移顺序：`0004-support-ingress-schema.sql`（建 `integration` / `support` 表）→ `0005-ingress-role.sql`（建 `saas_ingress` 角色与授权）。
2. 部署顺序：迁移 → `saas-api`（Ingress 端点生效）→ `saas-worker`；任何一步失败可只停 Worker，Ingress 继续落库不丢事件。
3. 回滚：先停 Worker，再回滚 `saas-api`，最后按 down migration 删表（会丢失未消费事件，仅限本地/未投产环境）。
4. 配置项：`CHATWOOT_WEBHOOK_SECRETS`、`WEBHOOK_MAX_BODY_BYTES`（默认 1048576）、`WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS`（默认 300）、`WORKER_POLL_MAX_SECONDS`（默认 5）。

## Open Questions

- 死信是否需要在上线前接入告警通道，还是在 `0022-observability-and-runbooks` 统一处理。
- `support_events` 的保留周期（`§3.5` 未给具体数值）在数据量出现后再定。
