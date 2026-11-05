import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export type ButtonProps = ComponentProps<"button"> & {
  variant?: "default" | "outline" | "ghost";
  size?: "default" | "sm";
};

/** 44 px tall on small screens, compact from md up. */
export function Button({ className, variant = "default", size = "default", ...props }: ButtonProps) {
  return (
    <button
      type="button"
      className={cn(
        "inline-flex items-center justify-center rounded-md font-medium transition-colors",
        "disabled:pointer-events-none",
        variant === "default" && "bg-accent text-accent-fg hover:brightness-110",
        variant === "outline" && "border border-border bg-surface text-text hover:bg-nav-active-bg",
        variant === "ghost" && "text-muted hover:bg-nav-active-bg hover:text-text",
        size === "sm" ? "min-h-11 px-3 py-1 text-caption md:min-h-8" : "min-h-11 px-4 py-2 text-body md:min-h-9",
        className,
      )}
      {...props}
    />
  );
}
