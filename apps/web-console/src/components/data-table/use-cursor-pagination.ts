import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

export type CursorPage<T> = {
  items: T[];
  next_cursor: string | null;
};

type UseCursorPaginationOptions<T> = {
  queryKey: readonly unknown[];
  fetchPage: (args: { cursor: string | null; pageSize: number }) => Promise<CursorPage<T>>;
  pageSize?: number;
};

/**
 * 游标分页：向前只记录已见过的游标栈，不推算页码。
 * 事实源 §12.1 规定分页使用 cursor + limit，禁止 offset。
 */
export function useCursorPagination<T>({
  queryKey,
  fetchPage,
  pageSize = 20,
}: UseCursorPaginationOptions<T>) {
  const [cursorStack, setCursorStack] = useState<Array<string | null>>([null]);
  const cursor = cursorStack[cursorStack.length - 1] ?? null;

  const query = useQuery({
    queryKey: [...queryKey, cursor, pageSize],
    queryFn: () => fetchPage({ cursor, pageSize }),
  });

  const nextCursor = query.data?.next_cursor ?? null;

  return {
    items: query.data?.items ?? [],
    isLoading: query.isLoading,
    error: query.error,
    cursor,
    hasNext: Boolean(nextCursor),
    hasPrev: cursorStack.length > 1,
    next: () => {
      if (nextCursor) {
        setCursorStack((stack) => [...stack, nextCursor]);
      }
    },
    prev: () => {
      setCursorStack((stack) => (stack.length > 1 ? stack.slice(0, -1) : stack));
    },
  };
}
