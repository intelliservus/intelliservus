# Proposal

## Why

`docs/项目开发文档.md` 的 §2.4 技术栈基线只把前端定为 "React 18 + TS 5 + TanStack Query + React Router"，对 UI 组件、样式方案、表单、图表、构建工具没有任何选型，§18 的 ADR 清单（ADR-001~012）也没有前端条目。若不先补齐这条决策并建立工程底座，M1 起的每个垂直切片都会各自决定一次组件与样式，控制台外观与交互必然漂移，§2.4 的"不引入重型 UI 框架依赖"也无从落地。

## What Changes

- 确立 `web-console` 前端工程基线：Vite + React 19 + TypeScript 5 + React Router + TanStack Query + TanStack Table + react-hook-form / zod + Tailwind CSS + shadcn/ui（Radix）+ Recharts + Playwright。
- 否决 Next.js 方案，评估过程与重新评估条件记入 ADR-013。
- `web-console` 保持静态部署单元（静态产物 + nginx），Docker Compose 拓扑与 §15.2 一致，不引入常驻 Node 服务。
- 建立控制台脚手架：应用外壳、路由与权限守卫骨架、API 客户端与错误信封映射、业务组件基建目录、Playwright 端到端骨架。
- 建立 monorepo、CI、Docker Compose 与数据库迁移框架等 M0 工程底座（§19 M0 工作项 4）。
- **不改动**任何已有或计划中的业务能力行为；本变更只交付工程底座与工具链。

## Capabilities

### New Capabilities

- 无。本变更是工程底座与工具链，不改变系统可观察行为，按 `skip_specs: true` 处理。`web-console` 能力规格推迟到首个包含控制台页面的垂直切片（M1）建立，届时同步在事实源文档 §1.4 与 §20.1 增补该能力。

### Modified Capabilities

- 无。

## Impact

- **代码**：新建 `web-console` 工作区及 monorepo 根配置；无既有代码受影响（当前仓库无实现代码）。
- **依赖**：前端依赖集合与版本见 `design.md`；CI 需增加前端 lint / typecheck / test 步骤。
- **接口**：无变更。控制台只消费既有 `/api/v1`，遵守 §12.1 的响应信封与 §12.2 的错误码目录。
- **部署**：`web-console` 以静态产物发布，Compose 服务需声明 healthcheck 与资源限制（§15.2）。
- **文档**：`docs/项目开发文档.md` §2.4 基线行、§18 ADR 表、§20.9 完成记录需更新；按 §D.2 属于"约束变化"，作为 tasks 中的待办项，本 change 不直接修改事实源文档。
- **前置依赖**：无。ADR-013 在本变更内关闭，M1 及之后的控制台实现以此为准。
