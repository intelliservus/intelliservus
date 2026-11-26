import { describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useCursorPagination, type CursorPage } from '@/components/data-table/use-cursor-pagination';

type Row = { id: string };

function createWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

function Probe({
  fetchPage,
}: {
  fetchPage: (args: { cursor: string | null; pageSize: number }) => Promise<CursorPage<Row>>;
}) {
  const page = useCursorPagination<Row>({ queryKey: ['rows'], fetchPage });

  return (
    <div>
      <ul>
        {page.items.map((item) => (
          <li key={item.id}>{item.id}</li>
        ))}
      </ul>
      <button onClick={page.next} disabled={!page.hasNext}>
        下一页
      </button>
      <button onClick={page.prev} disabled={!page.hasPrev}>
        上一页
      </button>
    </div>
  );
}

describe('useCursorPagination', () => {
  it('点击下一页时用返回的 cursor 请求下一段数据', async () => {
    const user = userEvent.setup();
    const fetchPage = vi.fn(
      ({ cursor }: { cursor: string | null; pageSize: number }): Promise<CursorPage<Row>> =>
        Promise.resolve(
          cursor === null
            ? { items: [{ id: 'a' }], next_cursor: 'cursor-1' }
            : { items: [{ id: 'b' }], next_cursor: null },
        ),
    );

    render(<Probe fetchPage={fetchPage} />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('a')).toBeDefined();
    });

    await user.click(screen.getByRole('button', { name: '下一页' }));

    await waitFor(() => {
      expect(screen.getByText('b')).toBeDefined();
    });
    expect(fetchPage).toHaveBeenLastCalledWith({ cursor: 'cursor-1', pageSize: 20 });
  });

  it('末页时下一页禁用，返回上一页恢复前一段', async () => {
    const user = userEvent.setup();
    const fetchPage = vi.fn(
      ({ cursor }: { cursor: string | null; pageSize: number }): Promise<CursorPage<Row>> =>
        Promise.resolve(
          cursor === null
            ? { items: [{ id: 'a' }], next_cursor: 'cursor-1' }
            : { items: [{ id: 'b' }], next_cursor: null },
        ),
    );

    render(<Probe fetchPage={fetchPage} />, { wrapper: createWrapper() });

    await waitFor(() => expect(screen.getByText('a')).toBeDefined());
    await user.click(screen.getByRole('button', { name: '下一页' }));
    await waitFor(() => expect(screen.getByText('b')).toBeDefined());

    const nextButton = screen.getByRole('button', { name: '下一页' }) as HTMLButtonElement;
    expect(nextButton.disabled).toBe(true);
    await user.click(screen.getByRole('button', { name: '上一页' }));

    await waitFor(() => expect(screen.getByText('a')).toBeDefined());
    expect(fetchPage).toHaveBeenLastCalledWith({ cursor: null, pageSize: 20 });
  });
});
