# Spec Delta

## Purpose

定义平台如何安全接收 Chatwoot 账户级 Webhook、把上游事件转换为内部标准事件、以及可靠地交给下游消费。本能力只管"接进来、验干净、排好队"，不决定是否回复、不推断租户归属、不保证处理顺序。

## ADDED Requirements

### Requirement: Webhook 投递验签

系统 SHALL 在解析 JSON 之前对原始请求体验签，算法为 `HMAC-SHA256(secret, "{timestamp}.{raw_body}")`，与 `X-Chatwoot-Signature` 做常数时间比较。校验顺序 MUST 为：内容类型 → 请求体大小 → 时间戳窗口 → 签名。默认上限 1MB、窗口 ±300 秒。

#### Scenario: 合法投递

- **WHEN** 请求携带正确的 `X-Chatwoot-Timestamp` 与匹配的 `X-Chatwoot-Signature`
- **THEN** 请求进入接收事务
- **AND** 响应不包含任何签名或 secret 片段

#### Scenario: 签名不匹配

- **WHEN** 签名与重算结果不一致
- **THEN** 返回 401
- **AND** 不写入 `webhook_deliveries`、`support_events` 与 `outbox_events`

#### Scenario: 时间戳越界

- **WHEN** `X-Chatwoot-Timestamp` 与服务端时间相差超过 300 秒
- **THEN** 返回 401 且不落库

#### Scenario: 缺少签名头或时间戳头

- **WHEN** 请求缺少 `X-Chatwoot-Signature` 或 `X-Chatwoot-Timestamp`
- **THEN** 返回 401 且不落库

#### Scenario: 请求体超限

- **WHEN** 原始请求体超过 1MB
- **THEN** 返回 413 且不解析、不落库

### Requirement: 投递去重

系统 SHALL 以 `(provider, account_id, delivery_key)` 唯一约束去重，`delivery_key` 优先取 `X-Chatwoot-Delivery`。重复投递 MUST 返回 200 且不创建新的处理任务。

#### Scenario: 重复投递

- **WHEN** 同一 `(provider, account_id, delivery_key)` 在时间窗内第二次到达
- **THEN** 返回 2xx
- **AND** 不新增 `support_events` 与 `outbox_events`

#### Scenario: 缺失 Delivery ID 的创建型事件

- **WHEN** 上游未提供 `X-Chatwoot-Delivery`，事件为 `message_created`、`contact_created` 或 `conversation_created`
- **THEN** 系统使用 §5.4 的复合键作为 `delivery_key`
- **AND** 在 `webhook_deliveries` 标记 `degraded = true`

#### Scenario: 缺失 Delivery ID 的更新型事件

- **WHEN** 上游未提供 `X-Chatwoot-Delivery`，事件为更新类型
- **THEN** 系统不使用消息级复合键去重，改为生成唯一键并标记 `degraded = true`
- **AND** 事件仍然入库，重复由业务层幂等吸收

### Requirement: 接收事务的原子性

系统 MUST 在同一事务内依次写入 `webhook_deliveries`、`support_events`、`outbox_events`，提交完成之后才返回 2xx。任何一步失败 MUST 返回 5xx，不得留下部分记录。

#### Scenario: 持久化失败

- **WHEN** 事务内任一步写入失败
- **THEN** 返回 5xx
- **AND** 三张表均无残留记录

#### Scenario: 提交成功

- **WHEN** 三张表写入成功并提交
- **THEN** 返回 2xx
- **AND** `outbox_events` 中存在对应待消费事件

### Requirement: 事件标准化

系统 SHALL 把上游事件转换为内部标准事件，只保留顶层字段与白名单子集。消息内容 MUST 以引用或摘要形式保存，禁止把完整 payload 整包落库当消息。

#### Scenario: 客户消息事件

- **WHEN** 收到 `message_created` 且发送方为联系人
- **THEN** 产生标准事件，含外部消息 ID、外部会话 ID、inbox ID、发送方类型、消息类型、`provider_created_at`
- **AND** `support_events.payload` 不包含会话历史的完整嵌套结构

#### Scenario: 上游内嵌会话历史

- **WHEN** payload 中携带完整会话历史
- **THEN** 系统只读取顶层字段并丢弃历史数组
- **AND** 记录的事件大小与历史长度无关

### Requirement: 自身消息与机器人消息过滤

系统 MUST 丢弃 AI 自身发送的消息、私有备注、其他机器人与自动化消息、平台系统消息。识别依据优先级 SHALL 为：上游 sender 类型 → 消息元数据标记 → 发送后本地登记的外部消息 ID 匹配。

#### Scenario: Agent Bot 自身消息

- **WHEN** 事件的 `sender.type` 为 `agent_bot`
- **THEN** 事件被标记为已过滤
- **AND** 不创建 `message_processing_records`

#### Scenario: 私有备注

- **WHEN** 事件携带 `private = true`
- **THEN** 事件被丢弃，不进入任何下游处理

#### Scenario: 其他机器人与系统消息

- **WHEN** sender 类型属于非人工、非客户的机器人或系统类型
- **THEN** 事件被丢弃
- **AND** 不产生公开回复

#### Scenario: 真实客户消息

- **WHEN** 事件来自联系人且不是私有备注
- **THEN** 事件被标记为可处理并进入业务幂等

### Requirement: 未映射事件的挂起

系统 MUST 只从映射表解析 workspace 与 channel。无法解析时 MUST 将事件置为 `pending_mapping`，不得投递下游，不得使用 payload 中的任何租户字段。

#### Scenario: 无映射

- **WHEN** 事件所属 account 或 inbox 尚无 workspace 映射
- **THEN** `support_events.status` 为 `pending_mapping`
- **AND** 不生成下游处理记录

#### Scenario: payload 携带伪造租户标识

- **WHEN** 请求体中包含 `tenant_id` 或 `workspace_id`
- **THEN** 系统忽略该字段
- **AND** 这些值不出现在任何写入与日志中

#### Scenario: 映射存在

- **WHEN** 映射表能解析出 tenant、workspace 与 channel
- **THEN** 事件带上解析结果并进入业务幂等
- **AND** 后续写入在对应租户的数据库上下文内完成

### Requirement: Outbox 可靠消费

系统 SHALL 以 `FOR UPDATE SKIP LOCKED` 单条领取待处理事件，消费方按 `event_id` 幂等。瞬时错误 MUST 按 2s/4s/8s/16s/32s 指数退避并带 ±20% 抖动，最多 5 次；超限置为 `dead_letter` 并保留完整信封。

#### Scenario: 正常消费

- **WHEN** Worker 领取到 `pending` 且已到期的事件
- **THEN** 事件状态变为 `processing`，处理后变为 `completed`

#### Scenario: 瞬时失败重试

- **WHEN** 处理过程中出现网络或上游 5xx 错误
- **THEN** 事件回到 `pending` 且 `available_at` 按退避延后
- **AND** `attempt` 递增，`trace_id` 保持为原始值

#### Scenario: 超过最大尝试次数

- **WHEN** 同一事件失败达到 5 次
- **THEN** 状态置为 `dead_letter`
- **AND** 完整信封与最后一次错误分类保留可查

#### Scenario: 同一事件重复消费

- **WHEN** 同一 `event_id` 被处理两次
- **THEN** 第二次不产生重复副作用

### Requirement: 业务层幂等

系统 MUST 以 `(message_id, processing_type)` 唯一约束保证同一消息的同一类处理只发生一次。冲突时 MUST 记为 `skipped_duplicate` 且不创建新的下游任务。

#### Scenario: 同一消息重复进入

- **WHEN** 同一消息以相同 `processing_type` 第二次进入处理
- **THEN** 本次处理结果记为 `skipped_duplicate`，已有处理记录保持不变
- **AND** 不创建第二个处理任务

#### Scenario: 不同处理类型

- **WHEN** 同一消息以不同 `processing_type` 进入
- **THEN** 允许各自生成处理记录

### Requirement: Ingress 最小权限与信息不泄露

Ingress 使用的数据库角色 MUST 只能写入接入侧表，不得读取任何租户业务数据。日志与响应 MUST NOT 包含 Webhook secret、签名原文或完整消息体。

#### Scenario: Ingress 尝试读取租户表

- **WHEN** 以 Ingress 角色的数据库上下文查询租户业务表
- **THEN** 查询被拒绝或返回空结果

#### Scenario: 记录访问日志

- **WHEN** 一次投递被处理
- **THEN** 日志包含 trace_id、事件类型与处理结果
- **AND** 不包含 secret、签名原文与完整消息体

### Requirement: Chatwoot 契约兼容

系统 SHALL 用固定版本的真实样本建立合约回放测试，覆盖消息创建、消息更新、会话事件、联系人事件、Agent Bot 与私有备注。上游字段变化导致回放失败时 MUST 阻断发布。

#### Scenario: 样本回放通过

- **WHEN** 以 Chatwoot `v4.20.1-ce` 采集的样本回放
- **THEN** 产生的事件类型、过滤结果与字段映射全部符合预期

#### Scenario: 上游字段变更

- **WHEN** 新版本 Chatwoot 的样本导致字段映射或事件类型不符
- **THEN** 合约测试失败
- **AND** 发布被阻断直至更新样本与适配逻辑
