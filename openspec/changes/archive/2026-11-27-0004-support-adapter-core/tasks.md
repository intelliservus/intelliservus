# Tasks

## 1. 数据模型与权限

- [x] 1.1 新增迁移 `apps/saas-api/migrations/0004-support-ingress-schema.sql`：建 `integration.webhook_deliveries`（唯一 `(provider, account_id, delivery_key)`）、`integration.outbox_events`（`(status, available_at)` 索引）、`integration.message_processing_records`（唯一 `(message_id, processing_type)`）、`support.support_events`（`delivery_id` 索引）、`support.conversations` / `support.messages` 最小字段集；验证：`uv run python scripts/migrate.py` 可在空库执行成功，且重复执行幂等
- [x] 1.2 新增迁移 `apps/saas-api/migrations/0005-ingress-role.sql`：创建 `saas_ingress` 角色，只授予三张接入表的 `INSERT`；验证：pytest 用例以该角色查询 `tenant.tenants` 被拒绝或返回空
- [x] 1.3 在 `modules/support_adapter/repositories.py` 实现投递、事件与 outbox 的写入/领取方法；验证：pytest 覆盖唯一冲突、事务回滚与 `SKIP LOCKED` 领取顺序

## 2. Ingress 接收

- [x] 2.1 实现 `POST /api/v1/ingress/chatwoot` 路由：读取原始体、校验内容类型、执行 1MB 上限；验证：超限返回 413、非 JSON 返回 400 且均不落库
- [x] 2.2 实现验签与配置加载：`HMAC-SHA256(secret, "{ts}.{raw}")`、常数时间比较、±300 秒时间窗、`CHATWOOT_WEBHOOK_SECRETS` 多 secret 支持；验证：签名不符、时间戳越界、缺失签名/时间戳头三类 401 单测通过，日志断言不含 secret 与签名原文
- [x] 2.3 实现接收事务：同一事务写 `webhook_deliveries` → `support_events` → `outbox_events`，提交后才返回 2xx；验证：注入写入失败时返回 5xx 且三张表无残留
- [x] 2.4 实现投递去重与降级键策略：`X-Chatwoot-Delivery` 优先，缺失时创建型事件用 §5.4 复合键、更新型事件用唯一键，均置 `degraded`；验证：重复投递返回 200 且不新增事件，两类缺失场景各有用例

## 3. 事件标准化与过滤

- [x] 3.1 实现 Chatwoot → 内部标准事件映射，仅保留顶层字段白名单（外部消息/会话/联系人 ID、inbox ID、sender 类型、消息类型、`private`、`provider_created_at`）；验证：测试断言 payload 中不含会话历史数组，事件大小与历史长度无关
- [x] 3.2 实现过滤链：`sender.type == agent_bot`、`private == true`、其他机器人与系统消息全部丢弃；验证：sender matrix 单测覆盖每一类且断言不生成处理记录
- [x] 3.3 定义 `MappingResolver` 端口与 `Unresolved` 返回；未解析事件置 `pending_mapping` 且不投递下游；验证：无映射时事件状态为 `pending_mapping`、`outbox_events` 无下游记录，payload 中伪造的 `tenant_id` 被忽略
- [x] 3.4 实现业务层幂等：`message_processing_records` 冲突即 `skipped_duplicate`；验证：同一 `(message_id, processing_type)` 第二次不产生新记录与新任务，不同 `processing_type` 各自成立

## 4. Outbox Worker

- [x] 4.1 新增独立 Worker 入口 `saas_api.worker`：可配置轮询，空闲时指数退避至上限；验证：启动成功后空队列下只有退避轮询日志，且不绑定 `PORT`
- [x] 4.2 实现领取与状态迁移（`pending` → `processing` → `completed`）；验证：两个 Worker 并发领取同一队列时不重复处理（集成测试）
- [x] 4.3 实现重试与死信：2s/4s/8s/16s/32s ±20% 抖动、`attempt` 递增、保留 `trace_id` 与 `retry_of`，5 次后 `dead_letter` 并保留信封；验证：失败注入用例在第 5 次后进入死信且信封完整
- [x] 4.4 在 `docker-compose.yml` 增加 `saas-worker` 服务（同镜像不同 command、健康检查、资源限制）；验证：`docker compose up -d` 后 worker 健康、`saas-api` 与 nginx 路由不受影响

## 5. 合约测试基线

- [x] 5.1 把 `spikes/chatwoot-poc/findings/samples` 中覆盖 `message_created`、`message_updated`、`conversation_*`、`contact_*`、`agent_bot`、`private` 的样本脱敏后固化到 `apps/saas-api/tests/contract/fixtures/chatwoot-4.20.1/`，每条带来源与采集日期元数据；验证：fixture 可被测试加载且不含真实联系人信息
- [x] 5.2 实现回放 harness：重算签名、调用 ASGI app、断言事件类型与字段映射；验证：`uv run pytest tests/contract` 通过，并加入 CI 的 Python job
- [x] 5.3 fixture 覆盖确认后处理 `spikes/chatwoot-poc/`（删除或归档，执行前与用户确认）；验证：仓库内无对 `spikes/chatwoot-poc` 的引用

## 6. 集成验证与文档回写

- [x] 6.1 用真实 Chatwoot 实例做端到端验证：配置账户级 Webhook、发送客户消息与私有备注，确认 `webhook_deliveries` / `support_events` / `outbox_events` 的写入与过滤结果；验证：记录一次完整运行的输出与查询结果
- [x] 6.2 回写文档：更新事实源 §19 M1 退出标准与附录 B 的阶段标注（AC-MSG-02 移交 `0007`）、修正 `0001` 结论表中 outbox 建表归属、在 §20.9 追加完成记录；在 `openspec/project.md` 补充 worker 启动命令；验证：diff 中上述修改齐全且 `openspec validate 0004-support-adapter-core --strict` 通过

## Workflow follow-up

- 全部任务完成并通过评审后归档变更，合并 `support-adapter` 增量到 `openspec/specs/`。
- 归档前确认 `0005-channel-mapping` 的 proposal 已引用本变更的 `MappingResolver` 端口与 `pending_mapping` 状态。
