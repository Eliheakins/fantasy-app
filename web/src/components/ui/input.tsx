import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export function Input({ className, type = "text", ...props }: ComponentProps<"input">) {
  return (
    <input
      type={type}
      className={cn(
        "min-h-11 w-full rounded-full border border-panel-line bg-surface px-3 py-2 text-base text-ink sm:text-body",
        "placeholder:text-muted disabled:cursor-not-allowed",
        className,
      )}
      {...props}
    />
  );
}
