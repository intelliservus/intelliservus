import type { ApiClient } from '@/api/client';

export type LoginInput = { email: string; password: string };

export type AccessTokenPayload = { access_token: string; expires_in: number };

export type SessionPayload = {
  user: { id: string; display_name: string };
  permissions: string[];
};

/** 认证端点自身不参与 401 自动刷新，否则 refresh 失败会递归重试。 */
const noRetry = { skipAuthRetry: true } as const;

export function createAuthApi(client: ApiClient) {
  return {
    login: (input: LoginInput) => client.post<AccessTokenPayload>('auth/login', input, noRetry),
    refresh: () => client.post<AccessTokenPayload>('auth/refresh', undefined, noRetry),
    logout: () => client.post<void>('auth/logout', undefined, noRetry),
    me: () => client.get<SessionPayload>('auth/me'),
  };
}

export type AuthApi = ReturnType<typeof createAuthApi>;
