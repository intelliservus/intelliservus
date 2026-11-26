import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import type { ApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';
import { AppRoutes } from '@/app/routes';
import { AuthProvider, useAuth } from '@/features/auth/auth-context';
import { tokenStore } from '@/features/auth/token-store';

function fakeClient(overrides: Partial<ApiClient>): ApiClient {
  return { request: vi.fn(), get: vi.fn(), post: vi.fn(), ...overrides } as unknown as ApiClient;
}

function SessionProbe() {
  const { session, logout } = useAuth();
  return (
    <div>
      <p>{session.status}</p>
      {session.status === 'authenticated' && <p>{session.user.displayName}</p>}
      <button onClick={() => void logout()}>退出</button>
    </div>
  );
}

describe('AuthProvider', () => {
  beforeEach(() => {
    tokenStore.set(null);
    localStorage.clear();
    sessionStorage.clear();
  });

  it('用 refresh cookie 换回 token 后加载当前主体', async () => {
    const client = fakeClient({
      post: vi.fn().mockResolvedValue({ access_token: 'token-1', expires_in: 900 }),
      get: vi.fn().mockResolvedValue({
        user: { id: 'u1', display_name: '张三' },
        permissions: ['agent:read'],
      }),
    });

    render(
      <AuthProvider client={client}>
        <SessionProbe />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText('authenticated')).toBeDefined();
    });
    expect(screen.getByText('张三')).toBeDefined();
    expect(tokenStore.get()).toBe('token-1');
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it('refresh 失败时进入匿名状态，且只请求一次', async () => {
    const client = fakeClient({
      post: vi.fn().mockRejectedValue(new ApiError({ code: 'AUTH_TOKEN_MISSING', message: '无会话', status: 401, retryable: false, traceId: 't' })),
    });

    render(
      <AuthProvider client={client}>
        <SessionProbe />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText('anonymous')).toBeDefined();
    });
    expect(tokenStore.get()).toBeNull();
    expect(client.post).toHaveBeenCalledTimes(1);
  });

  it('登出清除内存 token 并回到匿名状态', async () => {
    const client = fakeClient({
      post: vi.fn((path: string) =>
        path === 'auth/logout'
          ? Promise.resolve(undefined)
          : Promise.resolve({ access_token: 'token-1', expires_in: 900 }),
      ) as unknown as ApiClient['post'],
      get: vi.fn().mockResolvedValue({
        user: { id: 'u1', display_name: '张三' },
        permissions: [],
      }),
    });

    render(
      <AuthProvider client={client}>
        <SessionProbe />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText('authenticated')).toBeDefined();
    });

    screen.getByRole('button', { name: '退出' }).click();

    await waitFor(() => {
      expect(screen.getByText('anonymous')).toBeDefined();
    });
    expect(tokenStore.get()).toBeNull();
  });
  it('刷新失败后受保护路由跳转登录页', async () => {
    const client = fakeClient({
      post: vi.fn().mockRejectedValue(
        new ApiError({ code: 'AUTH_TOKEN_EXPIRED', message: '会话过期', status: 401, retryable: false, traceId: 't' }),
      ),
    });

    render(
      <AuthProvider client={client}>
        <MemoryRouter initialEntries={['/overview']}>
          <AppRoutes />
        </MemoryRouter>
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '登录控制台' })).toBeDefined();
    });
    expect(screen.queryByRole('heading', { level: 1, name: '工作台' })).toBeNull();
  });
});
