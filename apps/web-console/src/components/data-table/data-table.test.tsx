import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ColumnDef } from '@tanstack/react-table';
import { DataTable } from '@/components/data-table/data-table';

type Row = { id: string; name: string };

const columns: ColumnDef<Row, unknown>[] = [{ accessorKey: 'name', header: '名称' }];

describe('DataTable', () => {
  it('渲染数据行', () => {
    render(<DataTable columns={columns} data={[{ id: '1', name: 'Agent A' }]} />);

    expect(screen.getByText('Agent A')).toBeDefined();
    expect(screen.getByRole('columnheader', { name: '名称' })).toBeDefined();
  });

  it('空结果渲染空态', () => {
    render(<DataTable columns={columns} data={[]} emptyMessage="还没有 Agent" />);

    expect(screen.getByText('还没有 Agent')).toBeDefined();
  });

  it('请求失败渲染错误态', () => {
    render(<DataTable columns={columns} data={[]} errorMessage="加载失败" />);

    expect(screen.getByRole('alert').textContent).toContain('加载失败');
  });

  it('分页按钮按可用性禁用并触发回调', async () => {
    const user = userEvent.setup();
    const onNext = vi.fn();
    const onPrev = vi.fn();

    render(
      <DataTable
        columns={columns}
        data={[{ id: '1', name: 'Agent A' }]}
        pagination={{ hasNext: true, hasPrev: false, onNext, onPrev }}
      />,
    );

    const prevButton = screen.getByRole('button', { name: '上一页' }) as HTMLButtonElement;
    expect(prevButton.disabled).toBe(true);
    await user.click(screen.getByRole('button', { name: '下一页' }));
    expect(onNext).toHaveBeenCalledTimes(1);
    expect(onPrev).not.toHaveBeenCalled();
  });
});
