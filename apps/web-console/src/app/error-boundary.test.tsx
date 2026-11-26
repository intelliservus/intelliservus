import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { AppErrorBoundary } from '@/app/error-boundary';

function FailingQuery() {
  const { data } = useQuery({
    queryKey: ['failing'],
    queryFn: () => Promise.reject(new Error('查询失败')),
    retry: false,
    throwOnError: true,
  });

  return <div>{String(data ?? '')}</div>;
}

describe('全局错误边界', () => {
  it('Query 抛错时渲染兜底 UI 而不是白屏', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <AppErrorBoundary>
        <QueryClientProvider client={client}>
          <FailingQuery />
        </QueryClientProvider>
      </AppErrorBoundary>,
    );

    expect(await screen.findByRole('heading', { name: '页面出错了' })).toBeDefined();
    expect(screen.getByRole('alert')).toBeDefined();
  });
});
