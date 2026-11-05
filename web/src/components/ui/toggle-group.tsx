import { ToggleGroup as ToggleGroupPrimitive } from "radix-ui";
import { type ComponentProps, createContext, useContext } from "react";
import { cn } from "@/lib/utils";

type Size = "default" | "sm";
const SizeContext = createContext<Size>("default");

export function ToggleGroup({
  className,
  size = "default",
  children,
  ...props
}: ComponentProps<typeof ToggleGroupPrimitive.Root> & { size?: Size }) {
  return (
    <ToggleGroupPrimitive.Root className={cn("flex items-center justify-center gap-1", className)} {...props}>
      <SizeContext.Provider value={size}>{children}</SizeContext.Provider>
    </ToggleGroupPrimitive.Root>
  );
}

export function ToggleGroupItem({ className, ...props }: ComponentProps<typeof ToggleGroupPrimitive.Item>) {
  const size = useContext(SizeContext);
  return (
    <ToggleGroupPrimitive.Item
      className={cn(
        "inline-flex min-h-11 items-center justify-center rounded-md border border-border bg-surface font-medium text-muted transition-colors",
        "hover:bg-nav-active-bg hover:text-text disabled:pointer-events-none",
        "data-[state=on]:bg-nav-active-bg data-[state=on]:text-accent data-[state=on]:ring-1 data-[state=on]:ring-accent/35",
        size === "sm" ? "px-2.5 text-caption md:min-h-8" : "px-3 text-body md:min-h-9",
        className,
      )}
      {...props}
    />
  );
}
