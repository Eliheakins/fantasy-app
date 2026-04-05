import * as React from "react";

import { cn } from "@/lib/utils";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "outline" | "ghost";
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400 focus-visible:ring-offset-2",
        "disabled:pointer-events-none disabled:opacity-50",
        variant === "default" && "bg-zinc-900 text-zinc-50 hover:bg-zinc-800",
        variant === "outline" && "border border-zinc-700 bg-transparent hover:bg-zinc-900",
        variant === "ghost" && "hover:bg-zinc-800",
        "h-9 px-4 py-2",
        className,
      )}
      {...props}
    />
  ),
);
Button.displayName = "Button";
