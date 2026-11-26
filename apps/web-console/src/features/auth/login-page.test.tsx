import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router';
import type { ApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';
import { AuthProvider } from '@/features/auth/auth-context';
import { LoginPage } from '@/features/auth/login-page';
import { tokenStore } from '@/features/auth/token-store';

function fakeClient(): ApiClient {
  return {
    request: vi.fn(),
    get: vi.fn().mockResolvedValue({
      user: { id: 'u1', display_name: '张三' },
      permissions: ['agent:read'],
    }),
    post: vi.fn((path: string) => {
      if (path === 'auth/refresh') {
        return Promise.reject(
          new ApiError({
            code: 'AUTH_TOKEN_MISSING',
            message: '无会话',
            status: 401,
            retryable: false,
            traceId: 't',
          }),
        );
      }
      if (path === 'auth/login') {
        return Promise.resolve({ access_token: 'token-2', expires_in: 900 });
      }
      return Promise.resolve(undefined);
    }),
  } as unknown as ApiClient;
}

function renderLogin() {
  return render(
    <AuthProvider client={fakeClient()}>
      <MemoryRouter initialEntries={[{ pathname: '/login', state: { from: '/agents' } }]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/agents" element={<h1>Agent 列表</h1>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
}

describe('登录页', () => {
  beforeEach(() => {
    tokenStore.set(null);
    localStorage.clear();
    sessionStorage.clear();
  });

  it('登录成功后跳转来源页，token 只留在内存', async () => {
    const user = userEvent.setup();
    renderLogin();

    await user.type(await screen.findByLabelText('邮箱'), 'admin@example.com');
    await user.type(screen.getByLabelText('密码'), 'password123');
    await user.click(screen.getByRole('button', { name: '登录' }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Agent 列表' })).toBeDefined();
    });
    expect(tokenStore.get()).toBe('token-2');
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it('校验不通过时不发起登录请求', async () => {
    const user = userEvent.setup();
    renderLogin();

    await user.type(await screen.findByLabelText('邮箱'), 'not-an-email');
    await user.type(screen.getByLabelText('密码'), 'short');
    await user.click(screen.getByRole('button', { name: '登录' }));

    expect(await screen.findByText('请输入有效邮箱')).toBeDefined();
    expect(screen.getByText('密码至少 8 位')).toBeDefined();
    expect(screen.queryByRole('heading', { name: 'Agent 列表' })).toBeNull();
  });
});
