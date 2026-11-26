import type { FieldValues, Path, UseFormSetError } from 'react-hook-form';
import { ApiError } from '@/api/errors';

export type ServerFieldErrors = Record<string, string>;

function extractFieldErrors(details: unknown): ServerFieldErrors | null {
  if (typeof details !== 'object' || details === null) {
    return null;
  }

  const fields = (details as { fields?: unknown }).fields;
  if (typeof fields !== 'object' || fields === null) {
    return null;
  }

  const entries = Object.entries(fields as Record<string, unknown>).filter(
    (entry): entry is [string, string] => typeof entry[1] === 'string',
  );

  return entries.length > 0 ? Object.fromEntries(entries) : null;
}

/**
 * 把服务端 PARAM_INVALID 的 details.fields 映射到表单字段。
 * 返回 false 表示该错误不由字段级处理，交给页面顶部提示。
 */
export function applyServerFieldErrors<T extends FieldValues>(
  setError: UseFormSetError<T>,
  error: unknown,
): boolean {
  if (!(error instanceof ApiError) || error.code !== 'PARAM_INVALID') {
    return false;
  }

  const fields = extractFieldErrors(error.details);
  if (!fields) {
    return false;
  }

  for (const [name, message] of Object.entries(fields)) {
    setError(name as Path<T>, { type: 'server', message });
  }

  return true;
}
