# Proposal

## Why

M0 已用一次性 harness 验证了 Chatwoot 的上游事实（ADR-001/002/003/004/012），但生产侧一行 Ingress 代码都还没有：账户级 Webhook 无人接收、`webhook_deliveries` / `support_events` / `outbox_events` 三张表不存在、`§5.4` 的两层幂等键与 `§5.8` 的自身消息过滤链也没有实现。`0003` 已交付 `saas-api` 骨架、迁移执行器与事务上下文，使这层现在可以一次性落地；同时 `0005`（渠道映射）、`0007`（Runtime）都等待一个可用的标准化事件入口。

## What Changes

- 新增公开 Ingress 端点，接收 Chatwoot 账户级 Webhook，按 ADR-003 固定顺序执行：scheme → 原始体大小（≤1MB）→ 时间戳窗口（±5 分钟）→ `sha256=HMAC(secret, "{timestamp}.{raw_body}")` → 投递去重。验签失败或越界返回 401 且不落库；重复投递返回 200 且不新建任务。
- 建立接入侧数据模型：`integration.webhook_deliveries`（唯一键 `(provider, account_id, delivery_key)`）、`integration.outbox_events`、`integration.message_processing_records`、`support.support_events`，以及标准化落库所需的 `support.conversations` / `support.messages` 最小字段集。
- 实现 Support Adapter 的事件转换：只取顶层字段（禁止整包落库），按 §5.8 过滤自身消息、私有备注、其他机器人与系统消息，保留 `provider_created_at` / `provider_message_id` 供后续排序。
- 实现 outbox 消费 Worker：`FOR UPDATE SKIP LOCKED` 领取，指数退避（2s/4s/8s…，抖动 ±20%，最多 5 次，总时长 ≤10 分钟），超限进死信并保留完整信封；重试携带原始 `trace_id`、`attempt`、`retry_of`。
- 定义 `MappingResolver` 端口：解析 workspace/channel 只允许从映射表读取，不信任 payload 中的任何租户字段；无法解析时事件停在 `pending_mapping`，由 `0005` 落地后回填。
- 建立 Adapter 合约测试基线：把 `0001` 采集的真实事件样本脱敏后固化进仓库，按 Chatwoot `v4.20.1-ce` 的字段与版本差异做录制回放断言（§16.1 合约层）。
- Webhook secret 先由进程级环境变量提供，同时按 ADR-003 预留信封加密存储的升级路径。

## Capabilities

### New Capabilities

- `support-adapter`：Chatwoot 账户级 Webhook 的验签、防重放与投递去重，事件标准化与自身消息过滤，outbox 排队与重试/死信，以及 Adapter 合约测试基线。

### Modified Capabilities

- 无（`tenant-identity` 的既有要求不变；本变更只消费其 `tenant_context` 与 RLS 机制）。

## Impact

- **代码**：`apps/saas-api` 新增 `modules/ingress/`（验签与接收事务）与 `modules/support_adapter/`（事件转换与过滤）；新增独立 Worker 入口；新增迁移 `0004-*`。
- **接口**：新增公开 Ingress 端点（上游调用，不进入控制台契约）；`packages/api-contracts/openapi.yaml` 不新增管理端点。
- **数据**：新增 `integration` / `support` 两个 schema 下的 6 张表；不触碰 Chatwoot 库，不直连 Chatwoot 数据库。
- **部署**：`docker-compose.yml` 增加 `saas-worker` 单元与 Ingress 路由；Webhook 路径加入 nginx 反代。CI 的 Python job 增加合约回放测试。
- **文档**：更新事实源 §19 M1 退出标准与附录 B 的阶段标注（AC-MSG-02 移交 `0007`）；修正 `0001` 结论表中"`0003` 建 `outbox` 表"的失准记录；在 §20.9 留完成记录。
- **前置依赖**：`0001`（已归档，ADR-001~004）、`0003`（已归档，`saas-api` 骨架 + 迁移框架 + RLS）。不依赖未关闭的 ADR-005 / ADR-006 / ADR-011。
- **后续依赖**：`0005` 实现映射表与 `MappingResolver`；`0007` 消费标准事件并关闭 AC-MSG-02。

## Out of Scope

- **不做 Workspace ↔ Chatwoot Account / Inbox 映射与生命周期同步**：属 `0005-channel-mapping`。本变更只定义解析端口与 `pending_mapping` 状态，不创建 `support.chatwoot_mappings` / `support.channels`。
- **不做 AC-MSG-02（顺序、迟到、合并窗口、会话串行化）**：这些是 Conversation Coordinator 的职责，属 `0007-agent-runtime-a0`。本变更只保证排序字段与业务幂等键就位。
- **不做任何出站 Chatwoot API 调用**：AI 回复、状态改写在 `0007` / `0014`，且必须经 Outbound Security（`0013`）。
- **不做 Agent 推理、模型调用、知识检索**：分别属 `0007` / `0010` / `0009`。
- **不做死信的可视化与重投界面**：`§5.7` 的控制台入口留到有真实运维需求时单独立项。
- **不实现客户身份（T0–T3）与客户凭证**：属 `0012-customer-identity` 与 ADR-006。
- **不引入 Redis 通知与分布式锁**：ADR-004 已定 outbox 为事实源，Worker 轮询即可；Redis 唤醒留到压测暴露延迟问题后。
- **不在本变更关闭 ADR-005 / ADR-006**：它们是 `0007` / `0012` 的前置；M1 退出标准中这两项不由本变更负责。
