import type { ComponentProps } from "react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type Props = ComponentProps<typeof Input> & { id: string; label: string; wrapperClassName?: string };

/** A labelled text input: the label above the field, tied to it by `id`. */
export function Field({ id, label, wrapperClassName, ...inputProps }: Props) {
  return (
    <div className={cn("flex flex-col gap-1", wrapperClassName)}>
      <label htmlFor={id} className="text-body font-medium text-ink">
        {label}
      </label>
      <Input id={id} {...inputProps} />
    </div>
  );
}
