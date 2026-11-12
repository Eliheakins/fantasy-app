import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { UNAUTHORIZED_EVENT } from "@/api/envelope";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { ME_KEY, useSession } from "@/lib/session";

/** Shows the app only to a signed-in person. A request that comes back "unauthorized" (the session
 * ended while the page was open) makes the session check run again, which sends them to sign in. */
export function RequireSession() {
  const session = useSession();
  const queryClient = useQueryClient();
  const location = useLocation();
  const ended = useRef(false);

  useEffect(() => {
    const onUnauthorized = () => {
      ended.current = true;
      void queryClient.invalidateQueries({ queryKey: ME_KEY });
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [queryClient]);

  if (session.kind === "loading") {
    return (
      <p role="status" className="p-6 text-muted">
        Checking your sign-in…
      </p>
    );
  }
  if (session.kind === "signedOut") {
    const from = location.pathname + location.search;
    return <Navigate to="/login" replace state={{ from, ended: ended.current }} />;
  }
  if (session.kind === "error") {
    return (
      <section className="mx-auto max-w-page p-6">
        <PageHeader title="Could not check your sign-in" />
        <p role="alert" className="measure text-muted">
          {session.message}
        </p>
        <Button className="mt-4" onClick={session.retry}>
          Try again
        </Button>
      </section>
    );
  }
  return <Outlet />;
}
