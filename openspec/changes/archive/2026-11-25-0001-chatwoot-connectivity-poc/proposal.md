# Proposal

## Why

M0 的两半只完成了 `0002-engineering-baseline`（工程底座），`0001-chatwoot-connectivity-poc` 从未执行。事实源中大量 P0 设计都建立在尚未验证的上游能力上：接入方式（§5.1）、投递去重键（§5.4）、自身消息过滤（§5.8）、接管状态映射（§10.2）、Account 开通（§6.7）、队列方案（§12.4）。这些问题的答案决定 `0004-support-adapter-core` 的远端接口与 `0004`/`0005` 的实现难度。

§18 规定 ADR 未关闭不得合入依赖该决策的生产代码，而 ADR-001/002/003/004/012 全部"待定"。M0 退出标准的 6 项中仅有 CI 一项达成，其余 5 项均未满足，按 §0.2 与 §1.5 不得进入 M1 主体开发。

## What Changes

- 在 Docker Compose 中加入 Chatwoot CE（web + worker + 独立 PostgreSQL + 独立 Redis + 独立 network），镜像版本锁定；以 compose profile 隔离，使控制台开发路径不受影响。
- 建立一个**一次性**验证 harness（`spikes/chatwoot-poc/`），用 Chatwoot 自身的 public API 模拟客户消息，跑通最小闭环：接收 → 幂等落盘 → outbox 领取 → 调 API 回复 → 不触发自身循环。
- 采集并验证 7 项上游事实：webhook 事件全集与字段、Agent Bot 可用性、验签与防重放能力、事件唯一标识、`sender.type` 取值、接管事件语义、CE 的 platform API 开通能力。
- 关闭 ADR-001 / ADR-002 / ADR-003 / ADR-004 / ADR-012，按 §18 七要素写入 `docs/adr/`。
- 回写事实源：§18 ADR 状态、§19 M0 勾选项、§20.9 完成记录。

**明确不包含**（方案 B 的边界）：

- 不建立生产级 `apps/saas-api` 骨架、Ingress 模块或 Adapter。
- 不建立数据库迁移框架（该归属仍按 `0002` tasks 8.1 留在 `0003-tenant-rbac-foundation`）；POC 仅用单个 SQL 脚本 + scratch 表。
- 不编写任何能力规格；`support-adapter` 的真实规格在 `0004` 建立。
- 不修改 `apps/web-console` 或 `packages/`。

## Capabilities

### New Capabilities

- 无。本变更是验证与决策工作，不改变系统可观察行为，按 `skip_specs: true` 处理。POC harness 位于 `spikes/`，不构成受测的生产行为；`support-adapter` 能力规格推迟到 `0004-support-adapter-core`。

### Modified Capabilities

- 无。

## Impact

- **代码**：新增 `spikes/chatwoot-poc/`（一次性，`0004` 完成后删除或吸收）；`docker-compose.yml` 增加 `chatwoot` profile；不改 `apps/`、`packages/`、`openspec/specs/`。
- **依赖**：Chatwoot CE 镜像与配套 PostgreSQL/Redis（版本以 ADR-002 结论为准）；POC harness 的运行时依赖不进入 workspace lint / typecheck 门槛。
- **接口**：无对外接口变更。POC 接收端只监听本机，不进入 nginx 反代与 `/api/v1` 契约。
- **数据**：仅 POC scratch 表，随容器销毁，不进入平台库。
- **文档**：`docs/adr/` 新增 ADR-001/002/003/004/012；`docs/项目开发文档.md` §18、§19 M0、§20.9 需更新。
- **前置依赖**：`0002-engineering-baseline`（已归档）；无未关闭 ADR 阻塞本变更本身。
- **后续解锁**：`0003-tenant-rbac-foundation` 可在 M0 退出后开工；`0004-support-adapter-core` 以本变更的 ADR 为依据实现生产 Ingress。

## Out of Scope

- 真实渠道接入（Widget / 邮件 / 社交渠道）：POC 只用 Chatwoot 的 API 类型 Inbox 模拟客户。
- 模型推理、RAG、工具执行、身份体系、评测：均属后续阶段。
- 生产可观测性栈（OpenTelemetry collector、Langfuse）：按 §19 M0 工作项 5，结构化日志与最小 Trace 落到首个承载生产服务的 change（`0003`）。
- 性能与容量结论：POC 只验证正确性与能力可用性，不产出压测数据。
