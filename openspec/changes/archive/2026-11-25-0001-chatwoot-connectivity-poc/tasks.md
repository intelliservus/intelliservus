# Tasks

## 1. 前置与本地环境

- [x] 1.1 建立仓库首个提交（当前 `main` 无任何 commit），纳入现有 `web-console`、`packages/`、`openspec/` 与文档；验证：`git log --oneline` 至少 1 条提交，`git status --short` 干净，且 `docs/` 与 `openspec/` 均被跟踪
- [x] 1.2 在 `docker-compose.yml` 增加 `chatwoot` profile：`chatwoot-web`、`chatwoot-worker`、`chatwoot-postgres`、`chatwoot-redis`，独立 network `chatwoot-net`，显式 CPU/内存限制与 healthcheck，镜像锁定到具体版本并记录 digest；验证：`docker compose config` 通过；不带 profile 的 `docker compose up -d` 仍只起 `web-console`；`web-console` 与 `chatwoot-net` 无交集（`docker compose config` 输出中网络归属可核对）
- [x] 1.3 拉起 Chatwoot 并初始化：创建管理员、account 与一个 API 类型 Inbox，写入 `spikes/chatwoot-poc/scripts/seed.sh` 用于创建 contact / conversation / message，README 记录初始化步骤；验证：`docker compose --profile chatwoot up -d` 后 `docker compose ps` 全部 healthy，seed 脚本连续执行两次均成功生成新消息

## 2. 上游事实采集（阶段 A，只读）

- [x] 2.1 采集账号级 Webhook 的事件全集与字段：至少覆盖 `message_created`、`message_updated`、`conversation_updated`、`conversation_status_changed`，原始 payload 脱敏后存入 `spikes/chatwoot-poc/findings/`，并登记字段清单；验证：每个事件至少一份样本文件，字段清单可逐项对应到样本中的键路径
- [x] 2.2 验证 Agent Bot 通路：注册 bot、绑定 API Inbox、确认 bot 收到哪些事件、回包走哪个 API、bot 消息在事件中的归属；验证：`findings/agent-bot.md` 记录注册请求/响应、事件样本与回包结果，未验证项标注原因
- [x] 2.3 确定事件唯一标识、去重键与验签能力：检查全部请求 header 与 body，判断是否存在 Delivery ID、签名或时间戳；重放同一事件（含 `message_updated` 等更新类事件），按 §5.4 复合键验证唯一性；验证：`findings/delivery-identity.md` 给出 header 清单、重放实验结果，并明确"有/无签名"的判定
- [x] 2.4 确定自身消息识别依据：分别以 bot、人工客服、客户身份发消息，记录回调中的 `sender.type` / sender 结构与系统消息特征；验证：`findings/sender-matrix.md` 给出发送方 × 事件 × 字段取值的矩阵，明确 §5.8 三级优先级的判定依据
- [x] 2.5 采集人工接管事件语义：执行分配客服、接管、结束、重开、关闭，记录 `conversation_updated` 的字段与顺序，以及接管瞬间是否仍有 AI 发送窗口；验证：`findings/handoff-events.md` 给出状态迁移 → 事件 → 字段的对照表，并记录一次"接管与回复并发"的观测结果
- [x] 2.6 验证 CE 的 Account 开通能力：检查 super admin 是否提供 platform app / platform API，能否创建 account 与管理员；验证：`findings/account-provisioning.md` 给出可用性判定、所需 token 类型与权限，或失败的具体响应

## 3. 最小闭环 harness（阶段 B）

- [x] 3.1 实现 `spikes/chatwoot-poc/ingest.mjs`：接收 → 参数与大小校验 → 事务写 `poc_webhook_deliveries` / `poc_support_events` / `poc_outbox_events` → 2xx，重复投递直接返回成功；验证：同一 delivery 重投 10 次后，三张表各只有 1 条记录
- [x] 3.2 实现 `spikes/chatwoot-poc/outbox.mjs`：`FOR UPDATE SKIP LOCKED` 领取、指数退避重试、超过 5 次进死信；验证：注入一个必定失败的任务，断言重试次数为 5、状态为 dead letter，且同一任务不被两个 worker 同时领取
- [x] 3.3 实现 `spikes/chatwoot-poc/echo.mjs` 并跑通闭环：客户消息 → 平台 → 调 Chatwoot API 回复 → 客户侧可见；验证：一次完整往返在脚本输出中可追踪，回复消息出现在会话中
- [x] 3.4 实现自身消息过滤与接管静默：AI 回复触发的回调不得产生第二次回复；人工接管后的客户消息不得触发回复；验证：连续 3 轮自动回复后统计 AI 回复数为 3（无自循环）；接管后追加 2 条客户消息，AI 回复数保持不变
- [x] 3.5 验证并发不变量并固化复现方式：同会话并发注入 50 条消息，断言任意时刻同一会话只有 1 个处理者、每条客户消息只被一个 Run 覆盖（无重复回复）；把 4 条断言（闭环、去重、自身消息、接管静默）的运行命令写入 `spikes/chatwoot-poc/README.md`；验证：脚本重复运行 3 次结果一致，README 中的命令可照抄执行

## 4. ADR 与结论表

- [x] 4.1 写入 `docs/adr/ADR-001-chatwoot-ingress.md` 与 `ADR-002-chatwoot-version.md`：按 §18 七要素，ADR-001 必须包含消息闭环方式、自身消息过滤机制、人工接管语义、事件唯一标识、版本能力矩阵五项；验证：两份文件均含七要素标题，ADR-001 五项齐全，且每条结论可追到 `findings/` 中的样本
- [x] 4.2 写入 `docs/adr/ADR-003-webhook-authenticity.md` 与 `ADR-004-queue-implementation.md`：ADR-003 若无签名必须给出完整降级策略（通行令牌 / 来源限制 / 时间窗 / 去重）；ADR-004 必须回答 Redis 通知是否必需；验证：两份文件均含七要素与重新评估条件，且不含"待定"结论
- [x] 4.3 写入 `docs/adr/ADR-012-chatwoot-account-provisioning.md` 并在 change 内建立结论表（问题 → 结论 → 对下游 change 的影响 → 证据路径）：给出 A/B/C 判定与 V1 默认；验证：结论表覆盖 2.1–2.6 全部问题，每行都有证据路径，ADR-012 明确选定方案

## 5. 事实源回写与收口

- [x] 5.1 回写 `docs/项目开发文档.md`：§18 ADR 表五项状态改为已定并链接到 ADR 文件，§19 M0 勾选已完成项，§20.9 完成记录追加本 change；验证：§18 表格可跳转到对应 ADR，§19 与 3.5 的实测结果一致，§20.9 新行日期与 change 一致
- [x] 5.2 收口 `spikes/`：README 首行标注"非生产、0004 完成后删除或吸收"，确认根 `pnpm lint` / `pnpm typecheck` / `pnpm test` 不覆盖 `spikes/`，并记录 POC 代码的去留决定；验证：`pnpm lint` 与 `pnpm test` 在 `spikes/` 存在时仍通过，README 与设计文档 D8 一致

## Workflow follow-up

- 归档本 change；`0004-support-adapter-core` 以 `docs/adr/` 中五份 ADR 与结论表为实现依据。
- M0 退出标准满足后，才可开工 `0003-tenant-rbac-foundation`（§1.5）。
