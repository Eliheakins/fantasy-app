import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

type CalloutVariant = "warn" | "info";

const variantClass: Record<CalloutVariant, string> = {
  warn: "border-warning-edge bg-warning-bg text-warning",
  info: "border-line text-muted",
};

export interface CalloutProps {
  variant?: CalloutVariant;
  className?: string;
  children: ReactNode;
}

export function Callout({ variant = "info", className, children }: CalloutProps) {
  return <div className={cn("rounded-lg border px-3 py-2 text-body", variantClass[variant], className)}>{children}</div>;
}
