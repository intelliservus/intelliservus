import { ApiError } from '@/api/errors';

const DEFAULT_BASE_URL = '/api/v1';

export type ApiClientConfig = {
  baseUrl?: string;
  getAccessToken?: () => string | null;
  /** 401 时调用；返回新 token 则重试一次，返回 null 则放弃并抛错。 */
  onUnauthorized?: () => Promise<string | null>;
};

export type RequestOptions = {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
  headers?: Record<string, string>;
  /** 认证端点自身置 true，避免 401 递归触发刷新。 */
  skipAuthRetry?: boolean;
};

type ErrorEnvelope = {
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
    retryable?: boolean;
    trace_id?: string;
  };
};

function randomHex(byteLength: number): string {
  const bytes = new Uint8Array(byteLength);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
}

/** W3C traceparent：00-<trace-id>-<span-id>-01 */
function createTraceparent(): string {
  return `00-${randomHex(16)}-${randomHex(8)}-01`;
}

function resolveUrl(baseUrl: string, path: string): string {
  const url = `${baseUrl.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`;
  if (/^https?:\/\//.test(url)) {
    return url;
  }
  const origin = typeof window === 'undefined' ? 'http://localhost' : window.location.origin;
  return new URL(url, origin).toString();
}

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  return typeof value === 'object' && value !== null && 'error' in value;
}

export function createApiClient(config: ApiClientConfig = {}) {
  const baseUrl = config.baseUrl ?? DEFAULT_BASE_URL;
  const getAccessToken = config.getAccessToken ?? (() => null);

  async function send(path: string, options: RequestOptions): Promise<Response> {
    const requestId = crypto.randomUUID();
    const token = getAccessToken();

    const headers: Record<string, string> = {
      Accept: 'application/json',
      'X-Request-Id': requestId,
      traceparent: createTraceparent(),
      ...options.headers,
    };

    if (options.body !== undefined) {
      headers['Content-Type'] = 'application/json';
    }
    if (token && !headers.Authorization) {
      headers.Authorization = `Bearer ${token}`;
    }

    return fetch(resolveUrl(baseUrl, path), {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    });
  }

  async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    let response = await send(path, options);

    if (response.status === 401 && config.onUnauthorized && !options.skipAuthRetry) {
      const renewed = await config.onUnauthorized();
      if (renewed) {
        response = await send(path, {
          ...options,
          headers: { ...options.headers, Authorization: `Bearer ${renewed}` },
        });
      }
    }

    if (response.status === 204) {
      return undefined as T;
    }

    const payload: unknown = await response.json().catch(() => undefined);

    if (!response.ok) {
      const envelope = isErrorEnvelope(payload) ? payload : undefined;
      throw new ApiError({
        code: envelope?.error?.code ?? `HTTP_${response.status}`,
        message: envelope?.error?.message ?? response.statusText,
        status: response.status,
        retryable: envelope?.error?.retryable ?? (response.status >= 500 || response.status === 429),
        traceId: envelope?.error?.trace_id ?? response.headers.get('X-Request-Id') ?? '',
        details: envelope?.error?.details,
      });
    }

    if (typeof payload === 'object' && payload !== null && 'data' in payload) {
      return (payload as { data: T }).data;
    }
    return payload as T;
  }

  return {
    request,
    get: <T>(path: string, options: Omit<RequestOptions, 'method' | 'body'> = {}) =>
      request<T>(path, { ...options, method: 'GET' }),
    post: <T>(path: string, body?: unknown, options: Omit<RequestOptions, 'method' | 'body'> = {}) =>
      request<T>(path, { ...options, method: 'POST', body }),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
