import * as React from "react";

import { cn } from "@/lib/utils";

export type TextareaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement>;

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        "flex min-h-[120px] w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm",
        "text-zinc-100 placeholder:text-zinc-500",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-500",
        "disabled:cursor-not-allowed disabled:opacity-50",
        "font-mono",
        className,
      )}
      {...props}
    />
  ),
);
Textarea.displayName = "Textarea";
