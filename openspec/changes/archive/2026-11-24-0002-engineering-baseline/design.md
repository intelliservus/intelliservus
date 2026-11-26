# Design

> 本文件同时作为 **ADR-013 前端技术栈与渲染架构** 的决策记录，按 §18 要求包含背景、候选方案、约束、验证环境、最终决策、理由与重新评估条件。

## Context

- 事实源：`docs/项目开发文档.md`。约束集中在 §2.2（`web-console` 为独立部署单元）、§2.4（前端基线 `React 18 + TS 5 + TanStack Query + React Router`，且"不引入重型 UI 框架依赖"）、§2.5（`console → saas-api` 单向依赖、前端不得持有密钥）、§12.1（`/api/v1`、JWT、响应信封）、§12.2（错误码目录）、§15.2（Compose 健康检查与资源限制）。
- 当前仓库没有任何实现代码，`openspec/specs/` 与 `openspec/changes/` 均为空，本变更是第一个 change。
- 控制台形态已由事实源确定：登录后、全鉴权、多租户、无 SEO 需求、无公开页面；客服工作台由 Chatwoot CE 原生 UI 承担（§1.2、§10.2）。
- 事实源未定义前端 UI 组件、样式、表单、图表、构建工具，也没有对应 ADR。

## Goals / Non-Goals

**Goals:**

- 用一条决策关闭前端技术栈的空白，使 M1 起的垂直切片不再各自选型。
- 前端基线在满足"不引入重型 UI 框架依赖"的前提下，能覆盖 12 个管理模块的表格、表单、图表与排障视图。
- 部署形态与 §15.2 一致：`web-console` 仍是静态单元，不新增常驻服务进程。
- 认证与租户上下文严格遵循 §6.1：租户来自 token，不来自请求参数。

**Non-Goals:**

- 不实现任何具体业务页面；路由仅建立骨架，页面随各自垂直切片交付。
- 不建立 `web-console` 能力规格（见 proposal.md - Capabilities）。
- 不引入 SSR / RSC / BFF 层。
- 不确定 i18n、Storybook、主题定制等可选能力的引入时点。

## Decisions

### D1 渲染架构：SPA，否决 Next.js

| 候选 | 结论 | 理由 |
|---|---|---|
| **Vite + React Router（选用）** | 采纳 | 登录后内部系统，无 SEO 与首屏转化需求；全树交互密集，SSR/RSC 收益接近零；产物为静态文件，部署最简 |
| Next.js App Router + SSR | 否决 | 需新增常驻 Node 进程与 BFF 层，认证面从"浏览器直连 saas-api"变成"服务端转发用户凭证"，与 §2.5 单向依赖和 §14.2 密钥约束冲突；React 19 之外的版本组合会落后 |
| Next.js `output: 'export'` | 否决 | 静态导出后 RSC / middleware / 图片优化全部失效，退化为"文件路由 + 打包器"，收益不足以抵消框架体积与升级节奏 |

**重新评估条件**：出现面向客户的公开页面需求（状态页、文档站、Widget 配置页）时，新建独立应用承载，不在本应用内引入 Next。

### D2 依赖基线

| 层面 | 选型 | 说明 |
|---|---|---|
| 运行时 | React 19 | 事实源写 18，本 ADR 升级；shadcn/ui、TanStack Query v5、React Router 7 均已支持 |
| 语言 | TypeScript 5，`strict` | 与 §2.4 一致 |
| 构建 | Vite | 见 D1 |
| 路由 | React Router 7（声明式路由） | 保留 §2.4 原基线项 |
| 服务端状态 | TanStack Query v5 | 保留 §2.4 原基线项；所有 `/api/v1` 读取、缓存失效、重试的唯一入口 |
| 表格 | TanStack Table v8 | 与 Query 同源，12 个模块的列表页共用一套列定义与分页（游标）适配 |
| 表单与校验 | react-hook-form + zod | zod schema 与后端 Schema 描述对齐，表单错误映射到 §12.2 错误码 |
| 样式 | Tailwind CSS v4 | 编译期生成 CSS，零运行时 |
| 组件 | shadcn/ui（Radix 原语） | 源码复制进仓库，见 D3 |
| 图表 | shadcn chart（Recharts） | 运营看板与成本视图；大数据量场景见 Open Questions |
| 单元/组件测试 | Vitest + Testing Library + MSW | MSW 拦截 `/api/v1`，测试不依赖后端 |
| 端到端 | Playwright | §16.1 已指定 |
| 包管理 | pnpm workspace，Node 22 LTS | §2.4 基线 |

具体次版本在脚手架落地时锁定，由 `pnpm-lock.yaml` 固定（§2.4「锁定 lockfile」）。

### D3 组件方案：shadcn/ui + Tailwind 满足"不引入重型 UI 框架依赖"

对 §2.4 该约束的解读：禁的是**接管样式的整套组件框架**（Ant Design / MUI / Chakra 这类：npm 黑盒、主题能力有限、大版本破坏性升级）。

```text
        重型组件框架                shadcn/ui + Tailwind
        --------------------        -------------------------
形态     npm 依赖，黑盒              源码复制，仓库内可改
样式     受限于主题变量              完全自由
升级     被迫跟随大版本              按需手动合并
运行时   组件运行时 + 样式引擎       仅 Radix 无样式原语 + 编译期 CSS
```

因此本 ADR 明确边界：**允许**无样式可访问性原语（Radix）与工具类 CSS（Tailwind）；**禁止**引入替换整套视觉与交互的组件框架。

配套约定：

- 在 `components/ui`（shadcn 生成，视为第三方代码，不手改业务逻辑）之上建立 `components/<domain>` 业务封装层，业务页面只依赖业务封装层。
- 骨架、表格、表单、图表优先用 shadcn 官方 block/模板起步，减少自研面。

### D4 认证与凭证存放

| 凭证 | 存放 | 理由 |
|---|---|---|
| Access Token（JWT） | 内存（模块级变量） | XSS 无法从 `localStorage` 批量窃取；页面刷新丢失后由 refresh 换回 |
| Refresh Token | `httpOnly` + `Secure` + `SameSite=Strict` Cookie，仅由 `saas-api` 下发 | JS 不可读；`SameSite=Strict` 压制 CSRF |
| 密钥 / Webhook Secret / 完整业务凭证 | 一律不进前端 | §2.5 禁令 4、§14.2 |

- `POST /auth/refresh` 必须校验 `Origin`，并只接受 `POST`。
- 同源部署是 `SameSite=Strict` 生效的前提，见 D5。
- 401 统一由 API 客户端触发一次静默刷新，失败则跳转登录；刷新用并发去重，避免风暴。
- 前端不保存 `tenant_id` 作为授权依据：路径中出现 `tenant_id` / `workspace_id` 只用于定位，服务端以 token 推导（§6.1）。

### D5 部署形态：静态产物 + nginx 同源反代

```text
浏览器
  │  https://console.<host>/
  ├──────────────► nginx ── 静态文件（Vite 产物）
  │                  └── /api/v1/* ──► saas-api
  │
  └── 无跨域请求，Refresh Cookie 为第一方 Cookie
```

- 与 §2.2「`console → saas-api`」依赖方向一致，nginx 只做静态分发与反代，不承载业务逻辑。
- 同源避免 CORS，并让 `SameSite=Strict` Cookie 可用。
- Compose 服务需声明 healthcheck（`GET /healthz` 静态探针）与 CPU/内存限制（§15.2）。
- 不使用 CDN 或外部字体；构建产物内联所需静态资源，降低出站依赖面。

### D6 API 客户端与错误处理

- `packages/api-contracts`：由 saas-api 的 OpenAPI 生成 TS 类型（`openapi-typescript`，仅生成类型，不生成客户端），CI 校验生成结果无差异（§12.5 契约治理）。
- `apps/web-console/src/api`：薄封装 `fetch`，统一负责
  - 注入 `Authorization` 与 `traceparent` / `X-Request-Id`（§12.1、§13.1）；
  - 解包 `{ data, meta }` 信封；
  - 按 `error.code`（§12.2）映射为领域错误类型，`retryable` 决定 Query 是否重试；
  - 401 → 静默刷新；403 → 权限提示；`TENANT_SCOPE_MISMATCH` → 强制登出并告警。
- 全局错误展示只消费映射后的错误类型，不在页面里散写 `if (code === ...)`。

### D7 权限守卫（仅前端体验，不是授权）

- 路由级守卫：根据会话返回的角色/权限点决定是否渲染入口，**未授权路由不渲染任何业务组件**。
- 明确写入代码注释与文档：隐藏按钮不构成控制，后端强制校验（§1.3）。
- 守卫读取的权限来源是 `/api/v1/auth` 返回的当前主体信息，不信任 URL 参数。

### D8 目录结构（monorepo 目标形态）

```text
/
  pnpm-workspace.yaml
  apps/
    web-console/           # 本变更创建
      src/
        app/               # 路由表、布局、providers
        api/               # fetch 封装、错误映射、Query hooks
        components/ui/     # shadcn 生成组件（不手改）
        components/<domain># 业务封装层
        features/<module>/ # 按 §12.3 模块组织
        lib/               # 工具、格式化、权限判定
      e2e/                 # Playwright
    saas-api/              # 后续 change 创建
  packages/
    api-contracts/         # OpenAPI 生成类型
    config/                # 共享 tsconfig / eslint
```

## Risks / Trade-offs

| 风险 | 缓解 |
|---|---|
| shadcn 组件归自己维护，上游更新需手动合并 | 视为第三方代码，业务改动一律放 `components/<domain>`；升级时逐组件 diff |
| Tailwind v4 与部分插件/工具链仍在演进 | 以 `shadcn init` 官方生成的配置基线为准，不自行拼装 PostCSS 链路 |
| React 19 与个别库的 peer 依赖 | 锁定 lockfile；CI 启用严格 peer 检查 |
| "重型 UI 框架"边界被后续变更模糊化 | 本 ADR D3 已给出正/负清单，新增 UI 依赖需引用本 ADR 判定 |
| 静态同源部署依赖 nginx 配置，环境差异易出错 | 将 nginx 配置纳入仓库版本管理，Compose 内固定镜像 digest |
| OpenAPI 类型生成滞后于后端 | CI 生成并校验 diff，落后即失败 |
| 图表库在大数据量看板上可能不足 | 见 Open Questions，M6 运营模块落地前复评 |

## Migration Plan

- 全新工作区，无存量数据或代码迁移。
- 落地顺序：workspace 骨架 → 依赖锁定 → 路由与 provider → API 客户端 → 组件基建 → Playwright 骨架。
- 回滚：删除 `apps/web-console` 与根工作区配置即可，不影响其他服务；本变更不涉及数据库。

## Open Questions

- 图表库在 M6 运营看板的真实数据量下，Recharts 是否足够，还是需要 ECharts：不影响本 ADR 结构与任务拆分，M6 前复评。
- i18n 是否在 M1 引入：方案包 manifest 带 `language: zh-CN`（§17.1），但控制台本身的语言需求未定；M1 前决定。
- 是否需要 Storybook 承载组件文档：不影响前端基线选型与任务拆分，可后补。
