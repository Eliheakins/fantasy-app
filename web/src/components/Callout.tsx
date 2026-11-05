import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export type CalloutVariant = "error" | "warn" | "info";

const variantClass: Record<CalloutVariant, string> = {
  error: "border-warning bg-warning-bg text-warning",
  warn: "border-warning bg-warning-bg text-warning",
  info: "border-border bg-surface text-muted",
};

export interface CalloutProps {
  variant?: CalloutVariant;
  className?: string;
  children: ReactNode;
}

export function Callout({ variant = "info", className, children }: CalloutProps) {
  return <div className={cn("rounded-md border px-3 py-2 text-body", variantClass[variant], className)}>{children}</div>;
}
