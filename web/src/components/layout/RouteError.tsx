import { useRouteError } from "react-router";
import { Button } from "@/components/ui/button";

/**
 * The route error boundary. The usual cause is a redeploy: the open tab asks for a page chunk whose old hash
 * is gone, so a reload (which fetches the new index.html) fixes it.
 */
export function RouteError() {
  const error = useRouteError();
  const detail = error instanceof Error ? error.message : null;
  return (
    <main id="main" className="mx-auto w-full max-w-page px-4 py-10">
      <div role="alert" className="border-l-4 border-warning-edge bg-panel px-4 py-3">
        <h1 className="text-h1 font-semibold text-ink">This page could not load</h1>
        <p className="measure mt-2 text-body">A new version of the app may be live. Reload to get it.</p>
        {detail && <p className="mt-1 text-caption text-muted">{detail}</p>}
        <Button onClick={() => window.location.reload()} className="mt-3">
          Reload
        </Button>
      </div>
    </main>
  );
}
