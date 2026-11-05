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
        "inline-flex min-h-11 items-center justify-center rounded-full border border-panel-line bg-surface font-medium text-forest transition-colors",
        "data-[state=off]:hover:border-forest disabled:pointer-events-none",
        "data-[state=on]:border-forest data-[state=on]:bg-forest data-[state=on]:text-white",
        size === "sm" ? "px-2.5 text-caption md:min-h-8" : "px-3 text-body md:min-h-9",
        className,
      )}
      {...props}
    />
  );
}
