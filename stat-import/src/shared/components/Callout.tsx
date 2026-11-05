import type { ReactNode } from "react";

import { cn } from "@/shared/lib/utils";

export type CalloutVariant = "danger" | "warn" | "info";

const variantClass: Record<CalloutVariant, string> = {
  danger: "border-danger/25 bg-danger/5 text-danger-fg",
  warn: "border-warn-fg/25 bg-warn-fg/5 text-warn-fg",
  info: "border-border bg-input/40 text-ink-muted",
};

export interface CalloutProps {
  variant?: CalloutVariant;
  className?: string;
  children: ReactNode;
}

export function Callout({ variant = "info", className, children }: CalloutProps) {
  return <div className={cn("rounded-md border px-3 py-2 text-sm", variantClass[variant], className)}>{children}</div>;
}
