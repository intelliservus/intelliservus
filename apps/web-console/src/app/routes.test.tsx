import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { AppRoutes } from '@/app/routes';
import { appModules } from '@/app/modules';
import { SessionProvider, type SessionState } from '@/app/session';

const session: SessionState = {
  status: 'authenticated',
  user: { id: 'u1', displayName: '测试用户' },
  permissions: appModules.map((module) => module.permission),
};

function renderAt(path: string) {
  return render(
    <SessionProvider value={session}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </SessionProvider>,
  );
}

describe('空壳路由', () => {
  it.each(appModules.map((module) => [`/${module.path}`, module.title] as const))(
    '%s 渲染占位内容',
    (path, title) => {
      renderAt(path);

      expect(screen.getByRole('heading', { level: 1, name: title })).toBeDefined();
    },
  );

  it('未知路径渲染兜底页', () => {
    renderAt('/not-exists');

    expect(screen.getByRole('heading', { level: 1, name: '页面不存在' })).toBeDefined();
  });

  it('根路径重定向到工作台', () => {
    renderAt('/');

    expect(screen.getByRole('heading', { level: 1, name: '工作台' })).toBeDefined();
  });
});
