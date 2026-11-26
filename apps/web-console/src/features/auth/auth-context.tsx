import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { createApiClient, type ApiClient } from '@/api/client';
import { SessionProvider, type SessionState } from '@/app/session';
import { createAuthApi, type LoginInput, type SessionPayload } from '@/features/auth/auth-api';
import { createRefreshQueue } from '@/features/auth/refresh-queue';
import { tokenStore } from '@/features/auth/token-store';

type AuthContextValue = {
  session: SessionState;
  login: (input: LoginInput) => Promise<void>;
  logout: () => Promise<void>;
  /** 业务请求使用的客户端：401 时自动走刷新。 */
  api: ApiClient;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function toSession(payload: SessionPayload): SessionState {
  return {
    status: 'authenticated',
    user: { id: payload.user.id, displayName: payload.user.display_name },
    permissions: payload.permissions,
  };
}

export function AuthProvider({ children, client }: { children: ReactNode; client?: ApiClient }) {
  // 认证端点单独使用不带 401 重试的客户端，避免 refresh 失败时递归刷新。
  const authApi = useMemo(
    () => createAuthApi(client ?? createApiClient({ getAccessToken: tokenStore.get })),
    [client],
  );

  const [session, setSession] = useState<SessionState>({ status: 'loading' });

  const markAnonymous = useCallback(() => {
    setSession((previous) => (previous.status === 'anonymous' ? previous : { status: 'anonymous' }));
  }, []);

  const refresh = useCallback(async () => {
    try {
      const { access_token } = await authApi.refresh();
      tokenStore.set(access_token);
      return access_token;
    } catch {
      tokenStore.set(null);
      markAnonymous();
      return null;
    }
  }, [authApi, markAnonymous]);

  const refreshOnce = useMemo(() => createRefreshQueue(refresh), [refresh]);

  const api = useMemo(
    () =>
      client ??
      createApiClient({
        getAccessToken: tokenStore.get,
        onUnauthorized: refreshOnce,
      }),
    [client, refreshOnce],
  );

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      const token = await refresh();
      if (cancelled) {
        return;
      }
      if (!token) {
        markAnonymous();
        return;
      }

      try {
        const me = await authApi.me();
        if (!cancelled) {
          setSession(toSession(me));
        }
      } catch {
        tokenStore.set(null);
        if (!cancelled) {
          markAnonymous();
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [authApi, markAnonymous, refresh]);

  const login = useCallback(
    async (input: LoginInput) => {
      const { access_token } = await authApi.login(input);
      tokenStore.set(access_token);
      const me = await authApi.me();
      setSession(toSession(me));
    },
    [authApi],
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      tokenStore.set(null);
      markAnonymous();
    }
  }, [authApi, markAnonymous]);

  const value = useMemo<AuthContextValue>(
    () => ({ session, login, logout, api }),
    [session, login, logout, api],
  );

  return (
    <AuthContext.Provider value={value}>
      <SessionProvider value={session}>{children}</SessionProvider>
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error('useAuth 必须在 AuthProvider 内使用');
  }
  return value;
}

/** 供不强制依赖认证的组件（如布局）安全读取；无 Provider 时返回 null。 */
export function useOptionalAuth(): AuthContextValue | null {
  return useContext(AuthContext);
}
