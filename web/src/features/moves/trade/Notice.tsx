import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";

/** Amber notice: warnings and errors the server explains (deadline, busy, invalid trade). */
export function Notice({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div role="alert" className="my-2 flex flex-wrap items-center gap-3 rounded border border-warning-edge p-3 text-warning">
      <p className="min-w-0 flex-1">
        <strong>Warning:</strong> {children}
      </p>
      {action}
    </div>
  );
}

export function RetryButton({ onClick, children = "Try again" }: { onClick: () => void; children?: ReactNode }) {
  return (
    <Button variant="outline" onClick={onClick}>
      {children}
    </Button>
  );
}
