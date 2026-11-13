import { Navigate, Outlet } from "react-router";
import { useSession } from "@/lib/session";

/** Keeps the admin page's link and screen away from everyone else. The server is what refuses
 * them; this only spares a member a page of errors. Sits inside `RequireSession`. */
export function RequireAdmin() {
  const session = useSession();
  if (session.kind === "signedIn" && session.me.is_admin) return <Outlet />;
  if (session.kind === "loading") return null;
  return <Navigate to="/" replace />;
}
