# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`intelliservus` — a multi-tenant AI customer-service SaaS. This monorepo currently contains only the **platform admin console** (`apps/web-console`) plus shared packages; the backend services (`saas-api`, runtime, workers) described in the specs are planned but not yet in `apps/`.

The authoritative specification is `docs/项目开发文档.md` (**事实源** — when anything conflicts, it wins). `openspec/project.md` is a short always-loaded context summary; `docs/adr/` holds decision records. All docs are in Chinese; keep new specs, ADRs and code comments in the same register.

## Commands

Run from the repo root (pnpm workspace, Node 22, pnpm 10):

```bash
pnpm install
pnpm dev                 # vite dev server for web-console (port 5173)
pnpm build               # recursive build
pnpm lint                # eslint . at root
pnpm typecheck           # recursive tsc --noEmit
pnpm test                # recursive vitest run
docker compose up -d --build   # static console via nginx on :8080
```

Console-specific:

```bash
pnpm --filter web-console test -- src/api/client.test.ts   # single test file
pnpm --filter web-console exec vitest                      # watch mode
pnpm --filter web-console e2e                              # Playwright; builds + previews on :4173
pnpm --filter @intelliservus/api-contracts generate        # regenerate src/schema.d.ts
```

## Architecture

```
apps/web-console/        React 19 + Vite 7 SPA, deployed as static files behind nginx
packages/api-contracts/  openapi.yaml → generated TS types (schema.d.ts)
packages/config/         shared tsconfig.base / tsconfig.react and ESLint config
openspec/                change proposals + capability specs (see below)
```

`web-console` layering (`@/` → `apps/web-console/src`):

- `app/` — shell: router, layout, providers (QueryClient, error boundary), session context, permission guard, module registry.
- `api/` — thin `fetch` wrapper and error taxonomy.
- `features/<domain>/` — business feature code (currently `auth/`). Everything else is placeholder routes.
- `components/ui/` — shadcn-generated primitives; **no business logic** here.
- `components/form/`, `components/data-table/` — shared business wrappers.

Adding a console module touches two places that are not derived from each other: register it in `app/modules.ts` (routes + permission) and add it to `navItems` in `app/layout.tsx`. The `permission` string must match a permission emitted by the backend `auth/me` response.

### API layer

- Base URL `/api/v1`; nginx proxies it to `saas-api` in Docker. Responses use a `{ data, meta }` envelope — the client unwraps `data` automatically.
- Every request injects `Authorization`, `X-Request-Id` (UUID) and a W3C `traceparent`; this is required by the spec, not optional.
- Errors follow `{ error: { code, message, details, retryable, trace_id } }` and are thrown as `ApiError`. `src/api/errors.ts` maps the spec's §12.2 error-code catalog to domain kinds — **a new error code must be added there and covered by tests**.
- Pagination is cursor + limit only; use `components/data-table/use-cursor-pagination.ts` (offset pagination is forbidden by spec §12.1).
- Types for endpoints come from generated contracts. After editing `packages/api-contracts/openapi.yaml`, run `generate` and commit the result — CI runs `git diff --exit-code` and fails on uncommitted regeneration.

### Auth

- Access token lives **only in memory** (`features/auth/token-store.ts`); refresh token is an httpOnly `SameSite=Strict` cookie. Persisting tokens to storage is a spec violation and is asserted against in E2E.
- Startup flow: `POST /auth/refresh` → `GET /auth/me`. A 401 triggers `createRefreshQueue` (single-flight: concurrent 401s share one refresh); auth endpoints pass `skipAuthRetry` to avoid recursive refresh.
- `RequirePermission` and hidden nav entries are UX only — authorization is enforced by the backend.

### Testing

- Vitest + jsdom, tests colocated as `*.test.ts(x)`; MSW for HTTP. Playwright specs live in `apps/web-console/e2e/` and mock `/api/v1/**` with `page.route`.
- CI (`.github/workflows/ci.yml`) order: install → regenerate contracts → diff check → lint → typecheck → unit → Playwright.

## Deployment notes

`apps/web-console/nginx.conf` serves the SPA with history fallback, `/healthz`, and proxies `/api/v1/` using a Docker resolver so nginx starts even when `saas-api` is absent (requests then 502). `docker-compose.yml` sets healthcheck and CPU/memory limits.

## Working rules (from the specs — these are constraints, not suggestions)

- **Change-first**: every task must map to an `openspec/changes/<id>` change; no "while I'm here" edits. One change = one vertical slice, ≤20 tasks. Use the `openspec-propose` / `openspec-apply-change` / `openspec-archive-change` skills for that workflow.
- `openspec/specs/` records only **implemented** behavior, merged from changes on archive. Do not pre-write specs for unbuilt features — put plans in the change's proposal/design.
- Do not merge production code that depends on an unclosed ADR; scaffolding and interface stubs are allowed.
- Never connect to the Chatwoot database, bypass outbound security, persist credentials/tokens client-side, log secrets or full message bodies, or introduce a heavy UI framework (Ant Design / MUI / Chakra). Do not trust `tenant_id` / `workspace_id` from requests for authorization. Never auto-retry tool calls that ended `TIMEOUT_UNKNOWN`.
- If a change alters constraints, update `docs/项目开发文档.md` — it is the source of truth, not a summary of the code.

## Git workflow — never commit unless explicitly asked

- After editing code or files, **do not run `git commit`, `git push`, or any other git command that writes history or moves refs**. Read-only commands (`git status`, `git log`, `git diff`) are fine.
- End every change with a report of what was touched: each changed file, what changed in it, and anything the user needs to review or run. That report is how the user reviews the work; a commit would bury it.
- A request to "fix X" or "implement Y" is **not** an instruction to commit. Only an explicit ask ("commit this", "提交一下") authorizes a git write.
- If a skill's workflow says to commit (e.g. `product-optimize` commits per item, `openspec` task lists may include a commit step), skip that step and report instead — unless the user asked for it in this session.
- `docs/` is the local project-documentation directory and must **never** be committed or pushed to the remote. It stays out of git (already covered by `.gitignore`), so the authoritative spec `docs/项目开发文档.md` exists only on this machine — read it locally, and never try to `git add -f` it.
