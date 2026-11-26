import { BrowserRouter } from 'react-router';
import { AppRoutes } from '@/app/routes';

export function AppRouter() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
