# 结论表（0001 POC）

每个问题 → 结论 → 对下游 change 的影响 → 证据路径。`0004` 实现时以本表 + `docs/adr/` 为入口。

> 证据列指向的 `findings/` 与 `docs/adr/` 均为本地产物，不提交仓库（`spikes/`、`docs/` 在 `.gitignore` 中）。
> 远端只能看到结论本身；需要复核样本或重跑断言时，须在产出该 POC 的机器上进行。

| # | 问题 | 结论 | 对下游的影响 | 证据 |
|---|---|---|---|---|
| 1 | 接入方式选 Webhook 还是 Agent Bot | 账户级 Webhook 为唯一事实入口；Agent Bot 只作 AI 身份与 inbox 语义 | `0004` Ingress 只订阅账户级 webhook；`0005` 绑定 bot | `findings/agent-bot.md`、ADR-001 |
| 2 | 哪个 CE 版本 | `v4.20.1-ce` + pgvector 0.8.7-pg16 + redis 7.4.12 | 合约测试基线；升级流程见 §15.5 | ADR-002、`README.md` |
| 3 | 有没有签名 / Delivery ID | 有；HMAC-SHA256(secret, `ts.body`) + `X-Chatwoot-Delivery` | `0004` 直接实现验签，无需降级；秘密按 webhook 存储 | `findings/delivery-identity.md`、ADR-003 |
| 4 | 去重键怎么定 | 主键 `(provider, account_id, delivery)`；复合键只在缺失时兜底 | `0003`/`0004` 表结构；`integration.webhook_deliveries` 唯一约束 | ADR-003、§5.4 |
| 5 | 自身消息如何识别 | `sender.type == "agent_bot"`；私有备注也会回流 | `0004` 过滤链；`0014` A1 草稿必须按 `private` 过滤 | `findings/sender-matrix.md` |
| 6 | 人工接管如何判定 | 无专门事件；`meta.assignee.type == "user"` 或人工出站消息；bot 绑定会让 assignee 变成 bot | `0015` 接管状态机；不能用「assignee 非空」 | `findings/handoff-events.md` |
| 7 | 上游有无发送门禁 | 无；接管后仍可发送 | 发送前二次校验不可省（§7.5）；`0016` 并发测试 | `findings/handoff-events.md` |
| 8 | 队列方案 | outbox + `SKIP LOCKED`；静默 2 秒合并；5 次退避后死信 | `0003` 建表；`0004` worker；Redis 唤醒可选 | ADR-004 |
| 9 | CE 能否自动开通 Account | 能；Platform API 三步（Account / User / AccountUser） | `0003` 租户创建编排；PlatformApp token 进密钥管理 | `findings/account-provisioning.md`、ADR-012 |
| 10 | 出站到内网是否可行 | 默认不可行（SafeFetch）；需公网地址或显式开关 | `0013` Outbound Security 的部署前置；ADR-001 约束 | `findings/delivery-identity.md` |
| 11 | payload 规模 | 事件内嵌完整会话历史，随会话增长 | `0004` 只取顶层字段，禁止整包落库当消息 | `findings/README.md` |
| 12 | 事件重复 | 状态变更同时产生 `conversation_status_changed` + `conversation_updated` | 业务幂等按消息/会话状态做，不按事件条数 | `findings/README.md`、ADR-001 |

## M0 退出标准对应

| 退出项 | 状态 | 证据 |
|---|---|---|
| 一条命令起本地环境 | 达成 | `docker compose --profile chatwoot up -d` |
| 客户消息 → 平台 → 回复 → 客户 | 达成 | `assert-loop.mjs` |
| AI 自身消息不循环、重复投递不重复处理 | 达成 | `assert-loop.mjs`、`assert-harness.mjs dedup` |
| 人工接管后 AI 静默 | 达成 | `assert-loop.mjs` |
| ADR-001/002/003/004/012 有结论 | 达成 | `docs/adr/` |
| CI 跑通 lint + typecheck + 单测 | 项目已有；`spikes/` 不纳入 | `.github/workflows/ci.yml` |
