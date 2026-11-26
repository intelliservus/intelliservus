# 项目约定（OpenSpec 上下文）

> 事实源：`docs/项目开发文档.md`（V1.0）。本文件与事实源冲突时，**以事实源为准**，并回头修正本文件。
> 本文件只放"每次对话都要知道的上下文"，不复制规格内容。

## 1. 产品

面向多行业企业的通用型 AI 客服 SaaS：企业配置、部署、运营具备知识理解、业务工具调用、人工协同与质量评测能力的 AI 客服。

三个非目标：

1. 不基于 Chatwoot Captain / Copilot / Enterprise 专有能力构建 Agent。
2. 不直接读写 Chatwoot 数据库；Chatwoot API 是唯一业务集成边界。
3. 不重写客服工作台；人工客服使用 Chatwoot CE 原生 UI。

## 2. 技术栈基线

| 层面 | 基线 |
|---|---|
| Node / 包管理 | Node 22 LTS + pnpm（锁定 lockfile） |
| 后端 | NestJS 11，模块化单体，禁止跨模块直接写表 |
| 前端 | React 19 + TS 5 + Vite + React Router + TanStack Query |
| 前端 UI | Tailwind CSS v4 + shadcn/ui（Radix），不引入重型 UI 框架 |
| Python | 3.12 + uv（Runtime 锁定依赖哈希） |
| Agent | LangGraph，状态可持久化、可取消 |
| 数据库 | PostgreSQL 16 + pgvector 0.8，平台库与 Chatwoot 库分离 |
| 队列 | PostgreSQL outbox 为事实源 + Redis 通知 |
| 观测 | OpenTelemetry + 结构化日志 + Langfuse，W3C traceparent |
| 部署 | Docker Compose v2，一条命令起本地环境 |

## 3. 目录与模块边界

```text
apps/
  web-console/      React 管理控制台（静态产物 + nginx）
  saas-api/         NestJS 控制平面 + Ingress
packages/
  api-contracts/    OpenAPI 生成的 TS 类型
  config/           共享 tsconfig / ESLint
openspec/           规格与变更（见 §6）
docs/               事实源文档与 ADR
```

依赖方向：

```text
console → saas-api → (内部 API) → runtime / tool-executor / knowledge
runtime → model-gateway / knowledge / tool-executor / adapter
worker  → 任意服务（仅通过内部 API 或队列，不直连其数据库）
所有出站 → outbound-security（无例外）
```

## 4. 三套等级与四重门禁

| 体系 | 取值 | 控制什么 |
|---|---|---|
| 自治等级 | A0 影子 / A1 人工确认 / A2 自动回复 | 回复如何送达客户 |
| 工具风险 | R0 公开只读 / R1 身份后只读 / R2 低风险写 / R3 高风险 | 业务操作能否执行 |
| 客户身份信任 | T0 匿名 / T1 渠道验证 / T2 企业身份 / T3 二次认证 | 可访问的数据范围 |

三套体系相互独立。任何组合必须同时满足：**自治等级允许 + 风险等级允许 + 身份等级允许 + 会话状态允许**，四者取交集任意一项不满足即拒绝。

## 5. 常用命令

```bash
pnpm install                 # 安装依赖（锁 lockfile）
pnpm dev                     # 启动开发环境
pnpm test                    # 单元 / 集成测试
pnpm lint                    # lint + typecheck
uv run pytest                # Python 侧测试
docker compose up -d         # 起本地全栈
openspec list                # 查看进行中的 change
openspec list --specs        # 查看现行能力规格
```

## 6. OpenSpec 约定

- 任何开发任务必须先对应一个 `changes/<id>`，不允许"顺手改"。
- 一个 change 只交付一个垂直切片，任务数 ≤20，超了拆。
- **规格是增量式的**：`openspec/specs/` 只记录**已实现**的行为，由 change 归档时合并增量产生。不预先编写未实现能力的规格；未实现的想法放在 change 的 proposal/design 中。
- 规格使用 Requirement / Scenario，数值、错误码、状态名与事实源保持一致。

## 7. 禁令清单

1. 不直连 Chatwoot 数据库。
2. 不绕过 Outbound Security 发起任何外部请求。
3. 不信任请求里的 `tenant_id` / `workspace_id`——只用于定位，授权范围由 token 推导。
4. 不记录密钥、Webhook Secret、完整凭证与完整消息内容。
5. 前端不持有密钥、Webhook Secret 或完整业务凭证；隐藏按钮不构成授权。
6. 不在前端持久化 access token 与 tenant 授权信息。
7. `TIMEOUT_UNKNOWN` 的工具调用禁止自动重试。
8. 不引入替换整套视觉与交互的重型 UI 组件框架（Ant Design / MUI / Chakra 等）。

## 8. 文档索引

| 文档 | 用途 |
|---|---|
| `docs/项目开发文档.md` | **事实源**，冲突以此为准 |
| `docs/adr/` | ADR 完整决策过程 |
| `openspec/changes/` | 进行中的变更 |
| `openspec/specs/` | 现行能力规格（增量累积） |

ADR 未关闭时，不得合入依赖该决策的生产代码；允许脚手架、接口占位与测试。
