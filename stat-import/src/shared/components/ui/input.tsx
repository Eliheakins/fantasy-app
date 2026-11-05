import * as React from "react";

import { cn } from "@/shared/lib/utils";

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

const Input = React.forwardRef<HTMLInputElement, InputProps>(({ className, type = "text", ...props }, ref) => {
  return (
    <input
      type={type}
      className={cn(
        "min-h-[44px] w-full rounded-md border border-border bg-input px-3 py-2 text-base text-ink sm:text-sm",
        "placeholder:text-ink-muted focus:outline-none focus:ring-2 focus:ring-primary",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      ref={ref}
      {...props}
    />
  );
});
Input.displayName = "Input";

export { Input };
