## Purpose

定义平台用户如何登录、如何被授权，以及租户与工作空间的数据边界。所有管理 API 的可见性与可操作性由本能力约束；客户身份（T0–T3）与客户凭证不在本能力范围内。

## ADDED Requirements

### Requirement: 平台会话建立

系统 SHALL 通过 `POST /api/v1/auth/login` 校验邮箱与密码，成功时返回短期 access token，并以 `httpOnly`、`Secure`、`SameSite=Strict` Cookie 下发 refresh token。

access token 的有效期 SHALL 不超过 15 分钟；refresh token 的有效期 SHALL 不超过 30 天。响应体 MUST 使用 §12.1 的 `{ data, meta }` 信封。

#### Scenario: 登录成功

- **WHEN** 已存在且启用的用户提交正确的邮箱与密码
- **THEN** 返回 200，`data` 含 `access_token` 与 `expires_in`
- **AND** 响应携带 refresh Cookie，且 Cookie 不出现在响应体中

#### Scenario: 凭据错误

- **WHEN** 邮箱不存在、密码错误或用户已禁用
- **THEN** 返回 401，错误码为 `AUTH_TOKEN_INVALID`
- **AND** 响应不区分「邮箱不存在」与「密码错误」

#### Scenario: 跨站刷新请求

- **WHEN** `POST /api/v1/auth/refresh` 的 `Origin` 不在允许列表内
- **THEN** 返回 401，且不轮换 refresh token

### Requirement: 会话刷新与吊销

系统 SHALL 在 `POST /api/v1/auth/refresh` 时轮换 refresh token：旧 token 立即失效，新 token 写入 Cookie。

系统 MUST 检测 refresh token 复用：已轮换的 token 再次出现时，吊销该用户全部会话并写审计。

#### Scenario: 正常刷新

- **WHEN** 客户端携带有效的 refresh Cookie 调用刷新
- **THEN** 返回 200 与新的 access token
- **AND** 旧 refresh token 立即失效

#### Scenario: 复用已轮换的 token

- **WHEN** 同一个 refresh token 被使用第二次
- **THEN** 返回 401，该用户的全部会话被吊销
- **AND** 写入 `decision = deny` 的审计记录

#### Scenario: 登出

- **WHEN** 已登录用户调用 `POST /api/v1/auth/logout`
- **THEN** 返回 204，该 refresh token 失效，Cookie 被清除
- **AND** 该 access token 在剩余有效期内仍可通过 `GET /auth/me` 识别主体，但无法再刷新

### Requirement: 会话主体与权限点

系统 SHALL 通过 `GET /api/v1/auth/me` 返回当前主体的标识、显示名与权限点集合。权限点 SHALL 是后端授权判定的同一来源，前端守卫不得自行推导。

#### Scenario: 已认证主体

- **WHEN** 持有有效 access token 请求 `/auth/me`
- **THEN** 返回 200，`data.permissions` 为字符串数组

#### Scenario: 缺失或过期

- **WHEN** 未携带 access token，或 token 过期/被篡改
- **THEN** 返回 401，错误码为 `AUTH_TOKEN_MISSING` / `AUTH_TOKEN_EXPIRED` / `AUTH_TOKEN_INVALID`

### Requirement: 租户上下文由凭证推导

系统 SHALL 从 access token 推导租户与工作空间范围。请求参数或路径中的 `tenant_id` / `workspace_id` 只用于定位资源，不得作为授权依据。

#### Scenario: 请求范围与凭证不一致

- **WHEN** 认证主体属于租户 A，却请求租户 B 的资源
- **THEN** 返回 403，错误码为 `TENANT_SCOPE_MISMATCH`
- **AND** 写入拒绝审计

#### Scenario: 未认证访问管理 API

- **WHEN** 未认证请求访问任一管理 API
- **THEN** 返回 401，不返回任何业务数据

### Requirement: RBAC 与资源范围

系统 SHALL 按「功能权限 ∩ 资源范围」判定每一次管理 API 调用。资源范围 SHALL 至少区分租户、工作空间与本人。

权限校验 MUST 在后端执行；前端隐藏入口不构成授权。

#### Scenario: 缺少权限点

- **WHEN** 主体在目标工作空间内的角色缺少该操作所需的权限点
- **THEN** 返回 403，错误码为 `AUTH_FORBIDDEN`
- **AND** 写入 `decision = deny` 的审计记录

#### Scenario: 同租户跨工作空间

- **WHEN** 主体只属于工作空间 A，却访问同租户工作空间 B 的资源
- **THEN** 返回 403，不得返回 B 的任何数据

#### Scenario: 成员被移除

- **WHEN** 成员的成员关系被删除
- **THEN** 该成员后续请求立即返回 403
- **AND** 其已有 refresh token 被吊销

### Requirement: 租户与工作空间生命周期

系统 SHALL 支持创建、查询、更新租户；创建租户时 MUST 同时创建至少一个工作空间并把创建者设为该租户的管理员。

工作空间与成员的删除 SHALL 立即生效，并记录审计。

#### Scenario: 创建租户

- **WHEN** 平台管理员创建租户
- **THEN** 返回 201，响应含租户与首个工作空间标识
- **AND** 该租户内不存在其他租户的资源引用

#### Scenario: 删除成员

- **WHEN** 租户管理员删除某成员
- **THEN** 返回 204
- **AND** 该成员对租户内任何工作空间的访问立即被拒绝

### Requirement: 租户数据隔离

系统 MUST 保证任意租户无法读取、写入、导出另一租户的数据，覆盖全部管理 API。

#### Scenario: 跨租户读取

- **WHEN** 租户 A 的主体以任一资源标识发起读请求
- **THEN** 返回 403 或 404，且响应中不含租户 B 的任何字段

#### Scenario: 跨租户写入

- **WHEN** 租户 A 的主体提交指向租户 B 资源的写请求
- **THEN** 操作被拒绝，租户 B 的数据不发生变化

#### Scenario: 隔离回归

- **WHEN** 在 2 租户 × 每租户 2 工作空间的数据集上执行 AC-TEN-01 与 AC-TEN-02 用例
- **THEN** 全部负向用例被拒绝

### Requirement: 平台角色的业务数据边界

平台角色 SHALL 只能管理租户、工作空间与全局配置。平台角色 MUST NOT 读取或写入租户的业务数据（会话、消息、知识库、Agent 运行、工具执行）。

跨租户访问业务数据 SHALL 只能通过显式的扮演机制完成，该机制必须记录扮演者、目标租户、理由与时限，并产生租户可见的审计。本能力不提供该机制。

#### Scenario: 平台角色管理平台资源

- **WHEN** 平台角色调用租户或工作空间管理接口
- **THEN** 返回 200，响应只含平台资源字段

#### Scenario: 平台角色读取业务数据

- **WHEN** 平台角色请求某租户的会话、消息或知识库内容
- **THEN** 返回 403，错误码为 `AUTH_FORBIDDEN`
- **AND** 写入 `decision = deny` 的审计记录

#### Scenario: 平台角色权限点不含业务类型

- **WHEN** 平台角色调用 `GET /api/v1/auth/me`
- **THEN** `data.permissions` 中不出现任何业务数据类型前缀（`conversation:`、`message:`、`knowledge:`、`agent_run:`、`tool_execution:`）

### Requirement: 授权拒绝审计

系统 SHALL 对认证失败、授权拒绝与租户范围不匹配写入审计，记录主体、动作、资源、判定与时间。

#### Scenario: 拒绝可追溯

- **WHEN** 任一请求被 403 拒绝
- **THEN** `audit_logs` 中存在对应记录，`decision = deny`
- **AND** 记录不包含密码、token 或完整请求体
