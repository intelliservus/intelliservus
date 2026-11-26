import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { RequirePermission } from '@/app/require-permission';
import { SessionProvider, type SessionState } from '@/app/session';

function renderGuard(session: SessionState) {
  return render(
    <SessionProvider value={session}>
      <MemoryRouter initialEntries={['/secret']}>
        <Routes>
          <Route
            path="/secret"
            element={
              <RequirePermission permission="agent:read">
                <h1>受保护内容</h1>
              </RequirePermission>
            }
          />
          <Route path="/login" element={<h1>登录页</h1>} />
        </Routes>
      </MemoryRouter>
    </SessionProvider>,
  );
}

const authenticated = (permissions: string[]): SessionState => ({
  status: 'authenticated',
  user: { id: 'u1', displayName: '测试用户' },
  permissions,
});

describe('路由权限守卫', () => {
  it('有权限时渲染业务内容', () => {
    renderGuard(authenticated(['agent:read']));

    expect(screen.getByRole('heading', { name: '受保护内容' })).toBeDefined();
  });

  it('已登录但缺少权限时渲染拒绝页', () => {
    renderGuard(authenticated(['tenant:read']));

    expect(screen.getByRole('heading', { name: '无权访问' })).toBeDefined();
    expect(screen.queryByRole('heading', { name: '受保护内容' })).toBeNull();
  });

  it('未登录时跳转登录页', () => {
    renderGuard({ status: 'anonymous' });

    expect(screen.getByRole('heading', { name: '登录页' })).toBeDefined();
    expect(screen.queryByRole('heading', { name: '受保护内容' })).toBeNull();
  });
});
