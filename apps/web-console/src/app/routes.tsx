import { Navigate, Route, Routes } from 'react-router';
import { AppLayout } from '@/app/layout';
import { appModules } from '@/app/modules';
import { ModulePlaceholder } from '@/app/placeholder';
import { RequirePermission } from '@/app/require-permission';
import { LoginPage } from '@/features/auth/login-page';

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<AppLayout />}>
        <Route index element={<Navigate to="/overview" replace />} />
        {appModules.map((module) => (
          <Route
            key={module.path}
            path={module.path}
            element={
              <RequirePermission permission={module.permission}>
                <ModulePlaceholder title={module.title} description={module.description} />
              </RequirePermission>
            }
          />
        ))}
        <Route
          path="*"
          element={<ModulePlaceholder title="页面不存在" description="请从左侧导航选择模块" />}
        />
      </Route>
    </Routes>
  );
}
