import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { createApiClient } from '@/api/client';
import { createRefreshQueue } from '@/features/auth/refresh-queue';

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function errorEnvelope(code: string) {
  return { error: { code, message: '测试', details: {}, retryable: false, trace_id: 't' } };
}

function ok(data: unknown) {
  return HttpResponse.json({ data, meta: { request_id: 'r' } });
}

function guardedEndpoint(path: string) {
  return http.get(`*/api/v1/${path}`, ({ request }) =>
    request.headers.get('authorization') === 'Bearer fresh'
      ? ok({ path })
      : HttpResponse.json(errorEnvelope('AUTH_TOKEN_EXPIRED'), { status: 401 }),
  );
}

describe('401 刷新队列', () => {
  it('3 个并发 401 只触发 1 次刷新', async () => {
    let refreshCalls = 0;
    const queue = createRefreshQueue(async () => {
      refreshCalls += 1;
      // 模拟真实网络耗时，使三个 401 落在同一刷新窗口内
      await new Promise((resolve) => setTimeout(resolve, 10));
      return 'fresh';
    });

    server.use(guardedEndpoint('a'), guardedEndpoint('b'), guardedEndpoint('c'));

    const client = createApiClient({ getAccessToken: () => 'stale', onUnauthorized: queue });
    const results = await Promise.all([client.get('a'), client.get('b'), client.get('c')]);

    expect(refreshCalls).toBe(1);
    expect(results).toEqual([{ path: 'a' }, { path: 'b' }, { path: 'c' }]);
  });

  it('刷新失败时只尝试一次，所有请求都以 401 失败', async () => {
    let refreshCalls = 0;
    const queue = createRefreshQueue(() => {
      refreshCalls += 1;
      return Promise.resolve(null);
    });

    server.use(
      http.get('*/api/v1/*', () =>
        HttpResponse.json(errorEnvelope('AUTH_TOKEN_EXPIRED'), { status: 401 }),
      ),
    );

    const client = createApiClient({ getAccessToken: () => 'stale', onUnauthorized: queue });
    const results = await Promise.allSettled([client.get('a'), client.get('b'), client.get('c')]);

    expect(refreshCalls).toBe(1);
    expect(results.every((result) => result.status === 'rejected')).toBe(true);
  });

  it('刷新结束后下一次 401 会重新发起刷新', async () => {
    let refreshCalls = 0;
    const queue = createRefreshQueue(() => {
      refreshCalls += 1;
      return Promise.resolve('fresh');
    });

    await queue();
    await queue();

    expect(refreshCalls).toBe(2);
  });
});
