import { Toggle as TogglePrimitive } from "radix-ui";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export function Toggle({ className, ...props }: ComponentProps<typeof TogglePrimitive.Root>) {
  return (
    <TogglePrimitive.Root
      className={cn(
        "inline-flex min-h-11 items-center justify-center rounded-md bg-transparent text-body font-medium text-muted transition-colors",
        "hover:bg-nav-active-bg hover:text-text disabled:pointer-events-none",
        "data-[state=on]:bg-nav-active-bg data-[state=on]:text-accent data-[state=on]:ring-1 data-[state=on]:ring-accent/35",
        className,
      )}
      {...props}
    />
  );
}
