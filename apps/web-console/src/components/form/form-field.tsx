import { useFormContext, type FieldValues, type Path } from 'react-hook-form';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

type FormFieldProps<T extends FieldValues> = {
  name: Path<T>;
  label: string;
  type?: string;
  placeholder?: string;
};

export function FormField<T extends FieldValues>({
  name,
  label,
  type = 'text',
  placeholder,
}: FormFieldProps<T>) {
  const {
    register,
    formState: { errors },
  } = useFormContext<T>();

  const message = errors[name]?.message;

  return (
    <div className="space-y-1.5">
      <Label htmlFor={name}>{label}</Label>
      <Input
        id={name}
        type={type}
        placeholder={placeholder}
        aria-invalid={Boolean(message)}
        aria-describedby={message ? `${name}-error` : undefined}
        {...register(name)}
      />
      {typeof message === 'string' && (
        <p id={`${name}-error`} className="text-xs text-destructive">
          {message}
        </p>
      )}
    </div>
  );
}
