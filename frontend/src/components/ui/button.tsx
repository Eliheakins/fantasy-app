import * as React from "react";

import { cn } from "@/lib/utils";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "outline" | "ghost";
  size?: "default" | "sm";
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "default", ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center rounded-md font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-app",
        "disabled:pointer-events-none disabled:opacity-50",
        variant === "default" && "bg-primary text-surface hover:brightness-110",
        variant === "outline" && "border border-border bg-surface text-ink hover:bg-input",
        variant === "ghost" && "text-ink-muted hover:bg-input hover:text-ink",
        size === "sm" ? "h-8 px-3 py-1 text-xs" : "h-9 px-4 py-2 text-sm",
        className,
      )}
      {...props}
    />
  ),
);
Button.displayName = "Button";
