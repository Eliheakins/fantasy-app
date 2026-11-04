import { Link } from "react-router-dom";

import { cn } from "@/shared/lib/utils";

export function HomePage() {
  return (
    <main className="mx-auto flex max-w-lg flex-1 flex-col justify-center px-4 py-16">
      <h1 className="text-3xl font-bold tracking-tight text-ink">The Bridge</h1>
      <p className="mt-3 text-sm text-ink-muted">
        Football analytics in the browser. This landing page is a placeholder — open the workbench to explore data or
        ask questions.
      </p>
      <div className="mt-8">
        <Link
          to="/explore"
          className={cn(
            "inline-flex h-9 items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-surface transition-colors hover:brightness-110",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-app",
          )}
        >
          Open workbench
        </Link>
      </div>
    </main>
  );
}
