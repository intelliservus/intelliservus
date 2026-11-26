import { expect, test, type Page } from '@playwright/test';

const permissions = [
  'overview:read',
  'tenant:read',
  'workspace:read',
  'channel:read',
  'agent:read',
  'knowledge:read',
  'tool:read',
  'model:read',
  'evaluation:read',
  'analytics:read',
  'audit:read',
  'run:read',
];

function errorBody(code: string) {
  return {
    error: { code, message: '测试错误', details: {}, retryable: false, trace_id: 'e2e-trace' },
  };
}

async function mockAuthApi(page: Page) {
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname;

    if (path.endsWith('/auth/refresh')) {
      return route.fulfill({ status: 401, json: errorBody('AUTH_TOKEN_MISSING') });
    }
    if (path.endsWith('/auth/login')) {
      return route.fulfill({
        json: { data: { access_token: 'e2e-token', expires_in: 900 }, meta: { request_id: 'r' } },
      });
    }
    if (path.endsWith('/auth/me')) {
      return route.fulfill({
        json: {
          data: { user: { id: 'u1', display_name: 'E2E 用户' }, permissions },
          meta: { request_id: 'r' },
        },
      });
    }
    if (path.endsWith('/auth/logout')) {
      return route.fulfill({ status: 204, body: '' });
    }

    return route.fulfill({ status: 404, json: errorBody('RESOURCE_NOT_FOUND') });
  });
}

test('未登录访问受保护路由会跳到登录页', async ({ page }) => {
  await mockAuthApi(page);
  await page.goto('/overview');

  await expect(page.getByRole('heading', { name: '登录控制台' })).toBeVisible();
});

test('登录 → 进入控制台 → 登出，且凭证不落浏览器存储', async ({ page }) => {
  await mockAuthApi(page);
  await page.goto('/');

  await page.getByLabel('邮箱').fill('admin@example.com');
  await page.getByLabel('密码').fill('password123');
  await page.getByRole('button', { name: '登录' }).click();

  await expect(page.getByRole('heading', { level: 1, name: '工作台' })).toBeVisible();
  await expect(page.getByText('E2E 用户')).toBeVisible();

  const storage = await page.evaluate(() => ({
    local: { ...localStorage },
    session: { ...sessionStorage },
    cookies: document.cookie,
  }));
  expect(storage.local).toEqual({});
  expect(storage.session).toEqual({});
  expect(storage.cookies).not.toContain('e2e-token');

  await page.getByRole('button', { name: '登出' }).click();
  await expect(page.getByRole('heading', { name: '登录控制台' })).toBeVisible();
});
