import type { ComponentProps } from "react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type Props = ComponentProps<typeof Input> & { id: string; label: string; error?: string | null; wrapperClassName?: string };

/** A labelled text input: the label above the field, tied to it by `id`. An `error` shows under the input,
 * announced, and marks the input invalid and described by it. */
export function Field({ id, label, error, wrapperClassName, className, ...inputProps }: Props) {
  const errorId = error ? `${id}-error` : undefined;
  return (
    <div className={cn("flex flex-col gap-1", wrapperClassName)}>
      <label htmlFor={id} className="text-body font-medium text-ink">
        {label}
      </label>
      <Input
        id={id}
        aria-invalid={errorId ? true : undefined}
        aria-describedby={errorId}
        className={cn("aria-[invalid=true]:border-warning", className)}
        {...inputProps}
      />
      {error && (
        <p id={errorId} role="alert" className="text-body text-ink">
          {error}
        </p>
      )}
    </div>
  );
}
