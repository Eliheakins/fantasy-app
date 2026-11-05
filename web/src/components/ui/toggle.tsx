import { Toggle as TogglePrimitive } from "radix-ui";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export function Toggle({ className, ...props }: ComponentProps<typeof TogglePrimitive.Root>) {
  return (
    <TogglePrimitive.Root
      className={cn(
        "inline-flex min-h-11 items-center justify-center rounded-full bg-transparent text-body font-medium text-muted transition-colors",
        "data-[state=off]:hover:text-ink data-[state=off]:hover:border-focus disabled:pointer-events-none",
        "data-[state=on]:bg-forest data-[state=on]:text-white",
        className,
      )}
      {...props}
    />
  );
}
