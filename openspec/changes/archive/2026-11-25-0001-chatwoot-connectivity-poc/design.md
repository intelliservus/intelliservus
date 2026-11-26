# Design

> 本文件同时承载 ADR-001/002/003/004/012 的**决策框架与验证协议**。POC 结束后，按 §18 七要素把每条结论展开写入 `docs/adr/`，本文件保留结论摘要与证据索引。

## Context

- `0002-engineering-baseline` 已归档：monorepo、CI、`web-console`、`packages/api-contracts` 就位；`docker-compose.yml` 只有 `web-console` 一个服务。
- `openspec/specs/` 为空，没有任何能力规格。
- 迁移框架的归属已被 `0002` tasks 8.1 明确留给 `0003-tenant-rbac-foundation`；结构化日志与最小 Trace 按 §19 M0 工作项 5 落到首个承载生产服务的 change（`0003`）。
- 事实源 §18 规定 ADR 未关闭时不得合入依赖该决策的生产代码，只允许脚手架、接口占位与测试——这是"用 harness 代替生产服务"的直接依据。
- §5.2 / §5.4 / §5.8 / §10.2 / §12.4 的规则已写死，但所依赖的上游字段与能力全部未经实测。
- 开发机：Docker 29 / Compose v5，16 GB 内存；Chatwoot 三件套 + 独立库在容量内。

## Goals / Non-Goals

**Goals:**

- 用一次性 harness 回答 7 个上游事实问题，答案可复现、可追溯、可被 `0004` 直接引用。
- 五个 ADR 在本变更内关闭，且每条都带"重新评估条件"。
- M0 退出标准的 4 条行为断言（闭环、去重、自身消息、接管静默）在 POC 中得到实测。
- POC 的失败与不确定性暴露在 M0，而不是拖到 `0004`。

**Non-Goals:**

- 不产出任何被 `apps/` 引用的代码路径。
- 不在 POC 中设计平台数据模型；`poc_` 前缀表随容器销毁。
- 不追求真实渠道、模型推理、工具或身份能力。
- 不给性能结论；并发断言只验证正确性（≤1 在处理），不测吞吐。

## Decisions

### D1 用一次性 harness 代替生产 Ingress

| 候选 | 结论 | 理由 |
|---|---|---|
| **`spikes/chatwoot-poc/` 独立 harness（选用）** | 采纳 | 迁移框架未就绪；生产 Ingress 的正式归属是 `0004-support-adapter-core`；避免 `0003` 建立后又因 ADR 结论返工 |
| 在 `apps/saas-api` 内建最小 Ingress | 否决 | 会迫使本变更提前建服务骨架与迁移框架，与 `0002` 的归属调整冲突，且大部分代码在 `0004` 会被重写 |
| 纯手工 curl 验证，不写 harness | 否决 | 无法验证 outbox、重试与并发不变量；M0 的 4 条断言需要可重复执行 |

harness 的代码是**丢弃物**：`0004` 完成后删除或整段吸收，不在 `spikes/` 之上做增量演进。

### D2 Compose 用 profile 隔离 Chatwoot

```text
docker compose up -d                    # 仅 web-console（现有开发路径不变）
docker compose --profile chatwoot up -d # M0 全环境，一条命令
```

- Chatwoot web / worker / postgres / redis 全部挂在 `chatwoot` profile 与独立 network `chatwoot-net`。
- 平台侧服务（当前只有 `web-console`）**不得**加入 `chatwoot-net`；Chatwoot 也不得加入平台默认 network。这是 §15.2"网络分段"的最小可验证形态。
- 备选"独立 compose 文件"被否决：M0 退出标准要求一条命令起环境，两个文件需要额外包装脚本，反而更脆。

### D3 用 Chatwoot 的 API 类型 Inbox 模拟客户

不接 Widget、邮件或任何外部渠道。POC 通过 Chatwoot public API 直接造消息：

```text
POST /public/api/v1/inboxes/{inbox_identifier}/contacts
POST /public/api/v1/inboxes/{inbox_identifier}/contacts/{contact_id}/conversations
POST /public/api/v1/inboxes/{inbox_identifier}/contacts/{contact_id}/conversations/{conversation_id}/messages
```

- 优点：无需外部账号、SMTP 或前端页面，完全脚本化，可重复。
- 该路径与真实渠道共用同一套 `message_created` 事件，因此对 Ingress 的验证有效。
- 已知局限：渠道特有字段（如邮件主题、Widget 的 `hmac_verified`）不在 POC 覆盖范围，需在 ADR-001 的"重评估条件"中标注。

### D4 POC 持久化用 `poc_` 前缀 scratch 表

- 一个 `init.sql` 建三张表：`poc_webhook_deliveries`、`poc_support_events`、`poc_outbox_events`，字段按 §5.2 的最小需要，不追求完整。
- 表名带 `poc_` 前缀，避免被误认为平台 schema；随 compose volume 销毁。
- 正式 schema、迁移框架、RLS 全部留给 `0003`；本变更不产出 DDL 结论。

### D5 先观测、后实现的实验协议

```
阶段 A  只读采样（不写接收端）
        手动 curl / 垃圾桶端点 -> 原始 payload 原样存盘
        产出：字段清单、事件全集、header 清单
                     v
阶段 B  实现 harness，只消费阶段 A 已确认存在的字段
        产出：闭环 + 4 条断言
                     v
阶段 C  ADR 结论 + 结论表
```

硬性要求：任何结论必须附 **Chatwoot 版本 + 配置项 + 请求/响应样本 + 复现步骤**。没有样本的结论视为未验证。

### D6 ADR 产出格式

`docs/adr/ADR-00X-<slug>.md`，每份必须包含 §18 的七要素：

```text
背景 / 候选方案 / 约束 / 验证环境与版本 / PoC 结果 / 最终决策 / 重新评估条件
```

- ADR-001 额外必须记录五项：消息闭环方式、自身消息过滤机制、人工接管语义、事件唯一标识、版本能力矩阵（§5.1）。
- ADR-002 锁定具体 CE 版本，并给出升级回归的最小范围。
- ADR-003 若无签名能力，必须写明降级策略的具体实现（通行令牌 / 来源限制 / 时间窗 / 去重），不能只写"无签名"。
- ADR-004 必须回答：outbox 领取协议在真实事件节奏下是否够用，Redis 通知是否必需。
- ADR-012 必须给出 A/B/C 三案的判定与 V1 默认。
- **不允许以"待定"收尾**：若 POC 无法得出结论，写明阻塞原因、下一步实验与判定标准。

### D7 POC 结论表

除 ADR 外，在 change 内维护一张结论表（问题 → 结论 → 对下游 change 的影响 → 证据路径），归档时作为 `docs/adr/` 的索引。它是 `0004` 实现时的唯一入口。

### D8 `spikes/` 不进 CI 门槛

- 根 `pnpm lint` / `pnpm typecheck` / `pnpm test` 不覆盖 `spikes/`（在 ESLint ignore 与 workspace 配置中排除），避免一次性代码污染发布门禁。
- 但 harness 必须能一条命令运行，并在 README 记录运行前置与清理方式。
- 若 harness 需要测试，用独立 npm script，不并入 `pnpm test`。

## Risks / Trade-offs

| 风险 | 缓解 |
|---|---|
| Agent Bot 在 CE 能力弱于预期，ADR-001 只能落纯 Webhook | 阶段 A 优先验证第 2 问；若失败，在 ADR-001 写清 §5.8 的兜底路径（发送后登记外部消息 ID）并评估对 `0004` 的增量 |
| Chatwoot webhook 无签名、无 Delivery ID | ADR-003 直接给降级策略；§5.4 复合键必须在重放实验中验证唯一性，包括 `updated` 类事件 |
| Chatwoot 首次启动需初始化管理员 / 迁移耗时长 | 预拉镜像；用 env + seed 完成初始化并写入 README；不把首次启动时间算作结论 |
| harness 代码被误认为生产实现 | `spikes/*/README.md` 首行标注"非生产"；不进 CI；`0004` 归档时删除 |
| profile 差异导致 M0 冒烟漏测 | 冒烟脚本固定使用 `--profile chatwoot`；M0 退出验证必须在该命令下执行 |
| 接管竞态只在 demo 环境成立 | 阶段 B 显式做"接管与回复并发"注入，不留到 `0016` |
| 16 GB 内存下同时起全部服务吃紧 | Chatwoot 与其库显式声明资源限制；必要时 POC 期间只起 chatwoot profile |

## Migration Plan

- 无存量数据迁移，无生产影响。
- 落地顺序：仓库首次提交 → compose profile 与 Chatwoot 拉起 → 阶段 A 采样 → harness → 断言 → ADR 与文档回写 → 归档。
- 回滚：删除 compose 中的 `chatwoot` profile 服务、独立 network 与 `spikes/` 目录即可；不触碰 `apps/`、`packages/` 与 `openspec/specs/`。
- 归档前必须完成：五个 ADR 落盘、事实源 §18/§19/§20.9 回写、结论表就位。

## Open Questions

- POC 结论表是保留在归档 change 中，还是在 `docs/adr/` 下建一个索引文件？不影响任务拆分，归档时再定。
- `spikes/chatwoot-poc/` 在 `0004` 完成后删除还是保留为回归样本？取决于 harness 是否被 `0004` 的合约测试直接复用，M1 再定。
