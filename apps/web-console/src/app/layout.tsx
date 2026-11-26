import { NavLink, Outlet } from 'react-router';
import { useSession } from '@/app/session';
import { Button } from '@/components/ui/button';
import { useOptionalAuth } from '@/features/auth/auth-context';
import { cn } from '@/lib/utils';

const navItems = [
  { to: '/overview', label: '工作台' },
  { to: '/tenants', label: '租户' },
  { to: '/workspaces', label: '工作空间' },
  { to: '/channels', label: '渠道' },
  { to: '/agents', label: 'Agent' },
  { to: '/knowledge', label: '知识库' },
  { to: '/tools', label: '工具' },
  { to: '/models', label: '模型' },
  { to: '/evaluation', label: '评测' },
  { to: '/analytics', label: '运营' },
  { to: '/audit', label: '审计' },
  { to: '/runs', label: '运行' },
] as const;

export function AppLayout() {
  const session = useSession();
  const auth = useOptionalAuth();

  return (
    <div className="flex min-h-svh bg-background">
      <aside className="flex w-60 shrink-0 flex-col border-r bg-muted/30">
        <div className="flex h-14 items-center border-b px-6 text-sm font-semibold">
          AI 客服控制台
        </div>
        <nav className="flex-1 space-y-1 overflow-y-auto p-3" aria-label="主导航">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  'block rounded-md px-3 py-2 text-sm transition-colors',
                  isActive
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-between border-b px-6">
          <span className="text-sm text-muted-foreground">管理控制台</span>
          <div className="flex items-center gap-3">
            {session.status === 'authenticated' && (
              <span className="text-sm">{session.user.displayName}</span>
            )}
            {auth && session.status === 'authenticated' && (
              <Button variant="outline" size="sm" onClick={() => void auth.logout()}>
                登出
              </Button>
            )}
          </div>
        </header>
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
