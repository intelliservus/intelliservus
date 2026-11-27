export type ApiErrorKind =
  | 'unauthorized'
  | 'forbidden'
  | 'tenant_scope_mismatch'
  | 'not_found'
  | 'conflict'
  | 'validation'
  | 'rate_limited'
  | 'dependency'
  | 'server'
  | 'webhook'
  | 'message'
  | 'run'
  | 'model'
  | 'tool'
  | 'identity'
  | 'outbound'
  | 'knowledge'
  | 'unknown';

/** 事实源 §12.2 错误码目录到领域类别的映射。新增错误码必须同时更新此处。 */
export const API_ERROR_KINDS = {
  AUTH_TOKEN_MISSING: 'unauthorized',
  AUTH_TOKEN_INVALID: 'unauthorized',
  AUTH_TOKEN_EXPIRED: 'unauthorized',
  AUTH_FORBIDDEN: 'forbidden',
  TENANT_NOT_FOUND: 'not_found',
  TENANT_SCOPE_MISMATCH: 'tenant_scope_mismatch',
  RESOURCE_NOT_FOUND: 'not_found',
  RESOURCE_CONFLICT: 'conflict',
  PARAM_INVALID: 'validation',
  SCHEMA_VALIDATION_FAILED: 'validation',
  RATE_LIMITED: 'rate_limited',
  QUOTA_EXCEEDED: 'rate_limited',
  WEBHOOK_SIGNATURE_INVALID: 'webhook',
  WEBHOOK_TIMESTAMP_INVALID: 'webhook',
  WEBHOOK_PAYLOAD_TOO_LARGE: 'webhook',
  WEBHOOK_DUPLICATE: 'webhook',
  MESSAGE_SELF_LOOP: 'message',
  MESSAGE_ORDERING_DEGRADED: 'message',
  RUN_CANCELLED: 'run',
  RUN_SUPERSEDED: 'run',
  RUN_STALE_WRITE: 'run',
  RUN_TIMEOUT: 'run',
  MODEL_UNAVAILABLE: 'dependency',
  MODEL_TIMEOUT: 'dependency',
  MODEL_CONTENT_BLOCKED: 'model',
  TOOL_NOT_FOUND: 'tool',
  TOOL_NOT_BOUND: 'tool',
  TOOL_SCOPE_DENIED: 'tool',
  RISK_NOT_ALLOWED: 'tool',
  CONFIRMATION_REQUIRED: 'tool',
  IDEMPOTENCY_CONFLICT: 'tool',
  TOOL_TIMEOUT_UNKNOWN: 'tool',
  IDENTITY_INSUFFICIENT: 'identity',
  IDENTITY_CREDENTIAL_INVALID: 'identity',
  RESOURCE_NOT_OWNED: 'identity',
  OUTBOUND_BLOCKED: 'outbound',
  OUTBOUND_DNS_REBIND_DETECTED: 'outbound',
  OUTBOUND_SIZE_EXCEEDED: 'outbound',
  KNOWLEDGE_PARSE_FAILED: 'knowledge',
  KNOWLEDGE_NO_EVIDENCE: 'knowledge',
  SYS_INTERNAL: 'server',
  SYS_DEPENDENCY_UNAVAILABLE: 'dependency',
} as const satisfies Record<string, ApiErrorKind>;

export type ApiErrorCode = keyof typeof API_ERROR_KINDS;

export function classifyErrorCode(code: string): ApiErrorKind {
  return (API_ERROR_KINDS as Record<string, ApiErrorKind>)[code] ?? 'unknown';
}

export type ApiErrorInit = {
  code: string;
  message: string;
  status: number;
  retryable: boolean;
  traceId: string;
  details?: unknown;
};

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly retryable: boolean;
  readonly traceId: string;
  readonly details: unknown;

  constructor(init: ApiErrorInit) {
    super(init.message);
    this.name = 'ApiError';
    this.code = init.code;
    this.status = init.status;
    this.retryable = init.retryable;
    this.traceId = init.traceId;
    this.details = init.details;
  }

  get kind(): ApiErrorKind {
    return classifyErrorCode(this.code);
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}
