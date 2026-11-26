import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router';
import { useSession } from '@/app/session';

function ForbiddenPage() {
  return (
    <section role="alert" className="space-y-2">
      <h1 className="text-xl font-semibold">无权访问</h1>
      <p className="text-sm text-muted-foreground">
        当前账号缺少访问该模块的权限，请联系管理员分配角色。
      </p>
    </section>
  );
}

/**
 * 前端权限守卫只负责体验：未授权的入口不渲染业务组件。
 * 隐藏按钮与隐藏路由都不构成授权——权限始终由 saas-api 后端强制校验（事实源 §1.3）。
 */
export function RequirePermission({
  permission,
  children,
}: {
  permission: string;
  children: ReactNode;
}) {
  const session = useSession();
  const location = useLocation();

  if (session.status === 'loading') {
    return <p className="text-sm text-muted-foreground">正在加载当前账号信息…</p>;
  }

  if (session.status === 'anonymous') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  if (!session.permissions.includes(permission)) {
    return <ForbiddenPage />;
  }

  return children;
}
