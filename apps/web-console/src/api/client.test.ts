import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { createApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function errorEnvelope(code: string, message: string, retryable = false) {
  return {
    error: { code, message, details: {}, retryable, trace_id: 'trace-1' },
  };
}

describe('API 客户端', () => {
  it('注入 Authorization、X-Request-Id 与 traceparent，并解包 data 信封', async () => {
    let captured: Headers | null = null;

    server.use(
      http.get('*/api/v1/healthz', ({ request }) => {
        captured = request.headers;
        return HttpResponse.json({ data: { status: 'ok' }, meta: { request_id: 'r1' } });
      }),
    );

    const client = createApiClient({ getAccessToken: () => 'token-1' });
    const data = await client.get<{ status: 'ok' }>('healthz');

    expect(data).toEqual({ status: 'ok' });
    expect(captured).not.toBeNull();
    expect(captured!.get('authorization')).toBe('Bearer token-1');
    expect(captured!.get('x-request-id')).toMatch(/^[0-9a-f-]{36}$/);
    expect(captured!.get('traceparent')).toMatch(/^00-[0-9a-f]{32}-[0-9a-f]{16}-01$/);
  });

  it('错误响应转换为带领域类别的 ApiError', async () => {
    server.use(
      http.get('*/api/v1/agents', () =>
        HttpResponse.json(errorEnvelope('AUTH_FORBIDDEN', '无权限'), { status: 403 }),
      ),
    );

    const client = createApiClient();

    await expect(client.get('agents')).rejects.toMatchObject({
      code: 'AUTH_FORBIDDEN',
      status: 403,
      retryable: false,
      traceId: 'trace-1',
    });
  });

  it('401 时通过 onUnauthorized 换新 token 并重试一次', async () => {
    let calls = 0;

    server.use(
      http.get('*/api/v1/auth/me', ({ request }) => {
        calls += 1;
        if (request.headers.get('authorization') === 'Bearer fresh') {
          return HttpResponse.json({ data: { ok: true }, meta: { request_id: 'r2' } });
        }
        return HttpResponse.json(errorEnvelope('AUTH_TOKEN_EXPIRED', 'token 过期'), { status: 401 });
      }),
    );

    const client = createApiClient({
      getAccessToken: () => 'stale',
      onUnauthorized: () => Promise.resolve('fresh'),
    });

    await expect(client.get('auth/me')).resolves.toEqual({ ok: true });
    expect(calls).toBe(2);
  });

  it('无 onUnauthorized 时 401 直接抛 ApiError', async () => {
    server.use(
      http.get('*/api/v1/auth/me', () =>
        HttpResponse.json(errorEnvelope('AUTH_TOKEN_MISSING', '缺少凭证'), { status: 401 }),
      ),
    );

    const client = createApiClient();

    await expect(client.get('auth/me')).rejects.toBeInstanceOf(ApiError);
  });
});
