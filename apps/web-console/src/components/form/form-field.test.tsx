import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FormProvider, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { ApiError } from '@/api/errors';
import { FormField } from '@/components/form/form-field';
import { applyServerFieldErrors } from '@/components/form/server-errors';

const schema = z.object({ email: z.email('请输入有效邮箱') });
type Values = z.infer<typeof schema>;

function DemoForm({ submit }: { submit: (values: Values) => Promise<void> }) {
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: '' } });

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await submit(values);
    } catch (error) {
      applyServerFieldErrors(form.setError, error);
    }
  });

  return (
    <FormProvider {...form}>
      <form onSubmit={onSubmit} noValidate>
        <FormField<Values> name="email" label="邮箱" />
        <button type="submit">提交</button>
      </form>
    </FormProvider>
  );
}

describe('表单服务端错误映射', () => {
  it('PARAM_INVALID 的字段错误渲染到对应字段下', async () => {
    const user = userEvent.setup();
    const submit = vi.fn().mockRejectedValue(
      new ApiError({
        code: 'PARAM_INVALID',
        message: '参数不合法',
        status: 400,
        retryable: false,
        traceId: 't',
        details: { fields: { email: '邮箱已被占用' } },
      }),
    );

    render(<DemoForm submit={submit} />);

    await user.type(screen.getByLabelText('邮箱'), 'a@example.com');
    await user.click(screen.getByRole('button', { name: '提交' }));

    expect(await screen.findByText('邮箱已被占用')).toBeDefined();
    expect(submit).toHaveBeenCalledTimes(1);
  });

  it('非 PARAM_INVALID 错误不落到字段', async () => {
    const user = userEvent.setup();
    const submit = vi.fn().mockRejectedValue(
      new ApiError({
        code: 'RESOURCE_CONFLICT',
        message: '冲突',
        status: 409,
        retryable: false,
        traceId: 't',
        details: { fields: { email: '不应显示' } },
      }),
    );

    render(<DemoForm submit={submit} />);

    await user.type(screen.getByLabelText('邮箱'), 'a@example.com');
    await user.click(screen.getByRole('button', { name: '提交' }));

    expect(screen.queryByText('不应显示')).toBeNull();
  });
});
