# Tasks

## 1. 项目上下文与工程底座

- [x] 1.1 按 §20.2 创建 `openspec/project.md`（≤150 行：产品一句话与三个非目标、技术栈基线、目录与模块边界、三套等级与四重门禁、命令清单、禁令清单、事实源链接），并写明规格采用增量式——`specs/` 只记录已实现行为；验证：文件不超过 150 行且 §20.2 的 7 项内容齐全，`openspec list --specs` 仍为空
- [x] 1.2 建立 pnpm workspace 根（Node 22 LTS、`pnpm-workspace.yaml`、根 `package.json`），登记 `apps/*` 与 `packages/*`；验证：`pnpm install` 成功并生成 `pnpm-lock.yaml`，`pnpm -r list` 能列出工作区
- [x] 1.3 建立 `packages/config` 共享 `tsconfig`（`strict`）与 ESLint 配置，由 `web-console` 继承；验证：`pnpm -r exec tsc --noEmit` 通过，lint 对 `any` 与未使用变量报错
- [x] 1.4 建立 CI（GitHub Actions）：install → lint → typecheck → 单元测试；验证：PR 流水线全绿，向代码故意注入类型错误时流水线失败

## 2. web-console 脚手架

- [x] 2.1 用 Vite 创建 `apps/web-console`（React 19 + TypeScript 5），配置 `@/` 路径别名与 `src` 分层目录；验证：`pnpm --filter web-console build` 产出静态产物且无类型错误
- [x] 2.2 接入 Tailwind CSS v4 与 `shadcn init`，生成 `components.json` 与主题变量，锁定依赖次版本；验证：渲染一个 shadcn `Button` 后 `build` 成功，CI 中 `pnpm install --frozen-lockfile` 成功

## 3. 应用外壳与路由

- [x] 3.1 建立 `app/` 路由表与布局（侧栏 + 顶栏 + 内容区），按 §12.3 模块建立空壳路由占位；验证：每条路由可直接访问并渲染占位内容，刷新不 404
- [x] 3.2 建立 QueryClient provider 与全局错误边界；验证：组件测试中令 Query 抛错时错误边界渲染兜底 UI 而非白屏
- [x] 3.3 实现路由权限守卫：读取当前主体权限点，未授权路由不渲染任何业务组件，并在代码注释标注"隐藏按钮不构成授权（§1.3）"；验证：单元测试覆盖有权限 / 无权限 / 未登录三种分支

## 4. API 客户端与契约

- [x] 4.1 建立 `packages/api-contracts`，用 `openapi-typescript` 从 OpenAPI 生成类型；验证：重新生成后 `git diff --exit-code` 无差异，CI 中该步骤作为阻断项
- [x] 4.2 实现 `src/api` fetch 封装：注入 `Authorization` 与 `traceparent` / `X-Request-Id`，解包 `{ data, meta }` 信封；验证：MSW 单测断言请求头齐全且返回体被正确解包
- [x] 4.3 实现 `error.code` → 领域错误映射（含 `retryable` 与 401 / 403 / `TENANT_SCOPE_MISMATCH` 分支）；验证：单测逐条覆盖 §12.2 的初始错误码目录

## 5. 认证流

- [x] 5.1 实现登录 / 登出页面与 access token 内存存储 + `httpOnly` refresh cookie 流程，`POST /auth/refresh` 校验 Origin；验证：E2E 冒烟可登录、跳转控制台并登出，且全局检索确认 `localStorage` / `sessionStorage` 中无 token 与密钥
- [x] 5.2 实现 401 静默刷新与并发去重，失败跳转登录；验证：单测模拟 3 个并发 401 时仅触发 1 次 refresh，刷新失败时只跳转一次登录页

## 6. 组件基建

- [x] 6.1 以 shadcn 生成基础组件到 `components/ui`，并约定该目录不承载业务逻辑；验证：`components/ui` 与 shadcn 上游生成结果 diff 为空（仅主题变量除外）
- [x] 6.2 建立 `components/<domain>` 业务封装层与 DataTable 封装（游标分页、筛选、空态 / 错误态）；验证：组件测试覆盖游标推进、空结果与请求失败三种情况
- [x] 6.3 建立表单封装（react-hook-form + zod），把服务端 `PARAM_INVALID` 映射到对应字段；验证：组件测试断言错误码被渲染到目标字段下方

## 7. 部署与端到端

- [x] 7.1 编写 nginx 配置（静态分发 + `/api/v1` 反代 + `/healthz`）并纳入仓库，在 Compose 中声明 `web-console` 的 healthcheck 与 CPU / 内存限制；验证：`docker compose up -d` 后 `docker compose ps` 显示 healthy，控制台可访问
- [x] 7.2 建立 Playwright E2E 骨架：登录 → 访问一个空壳路由 → 登出；验证：CI 中 E2E 用例通过并保留 trace

## 8. 事实源同步

- [x] 8.1 同步事实源与 ADR：① 更新 `docs/项目开发文档.md` §2.4 前端基线行为本 ADR 选型；② §18 ADR 表新增 ADR-013（状态：已定）；③ §19 M0 工作项 4 的"数据库迁移框架"归属调整为 `0003-tenant-rbac-foundation`，工作项 5"结构化日志与最小 Trace"归属调整为首个承载服务的 change（`0001` 或 `0003`）；④ 在 `docs/adr/ADR-013-frontend-stack.md` 记录完整过程（以本 change 的 `design.md` 为源）。验证：文档 diff 通过评审，§18 表格可跳转到 ADR 文件，选型表与 `design.md` 逐项一致，§19 M0 工作项 4/5 的归属描述与已创建的 change 名一致

## Workflow follow-up

- 归档时在 `docs/项目开发文档.md` §20.9 完成记录追加一行（change = `0002-engineering-baseline`）。
- 首个包含控制台页面的 M1 变更中新建 `web-console` 能力规格，并同步在 §1.4 与 §20.1 增补该能力。
