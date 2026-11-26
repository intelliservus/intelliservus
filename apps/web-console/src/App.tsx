import '@/index.css';
import { AppErrorBoundary } from '@/app/error-boundary';
import { AppProviders } from '@/app/providers';
import { AppRouter } from '@/app/router';
import { AuthProvider } from '@/features/auth/auth-context';

export function App() {
  return (
    <AppErrorBoundary>
      <AppProviders>
        <AuthProvider>
          <AppRouter />
        </AuthProvider>
      </AppProviders>
    </AppErrorBoundary>
  );
}
