import { describe, expect, it } from 'vitest';
import { API_ERROR_KINDS, ApiError, classifyErrorCode } from '@/api/errors';

function apiError(code: string, overrides: Partial<ConstructorParameters<typeof ApiError>[0]> = {}) {
  return new ApiError({
    code,
    message: '测试',
    status: 400,
    retryable: false,
    traceId: 'trace-1',
    ...overrides,
  });
}

describe('错误码映射', () => {
  it('事实源 §12.2 的每个错误码都有领域类别', () => {
    const codes = Object.keys(API_ERROR_KINDS);

    expect(codes.length).toBeGreaterThanOrEqual(40);
    for (const code of codes) {
      expect(classifyErrorCode(code), code).not.toBe('unknown');
    }
  });

  it('未登记的错误码归类为 unknown', () => {
    expect(classifyErrorCode('SOMETHING_NEW')).toBe('unknown');
    expect(apiError('SOMETHING_NEW').kind).toBe('unknown');
  });

  it('401 类错误码归为 unauthorized', () => {
    expect(apiError('AUTH_TOKEN_MISSING').kind).toBe('unauthorized');
    expect(apiError('AUTH_TOKEN_INVALID').kind).toBe('unauthorized');
    expect(apiError('AUTH_TOKEN_EXPIRED').kind).toBe('unauthorized');
  });

  it('403 与租户范围不匹配有独立类别', () => {
    expect(apiError('AUTH_FORBIDDEN').kind).toBe('forbidden');
    expect(apiError('TENANT_SCOPE_MISMATCH').kind).toBe('tenant_scope_mismatch');
  });

  it('保留错误信封中的 retryable 与 traceId', () => {
    const error = apiError('RATE_LIMITED', { retryable: true, status: 429, traceId: 'trace-9' });

    expect(error.retryable).toBe(true);
    expect(error.status).toBe(429);
    expect(error.traceId).toBe('trace-9');
  });
});
