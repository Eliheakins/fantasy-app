import { NavLink, Outlet } from "react-router-dom";
import { Footer } from "./Footer";
import { StatusBanner } from "./StatusBanner";
import { TopBar } from "./TopBar";
import { NAV_ITEMS } from "@/nav";
import { cn } from "@/lib/utils";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex items-center gap-2 text-body",
    isActive ? "font-semibold text-accent" : "text-muted hover:text-text",
  );

/** Left rail from 768 px up, bottom tab bar below. */
export function AppShell() {
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <nav aria-label="Main" className="hidden w-48 shrink-0 border-r border-border p-4 md:block">
        <ul className="flex flex-col gap-1">
          {NAV_ITEMS.map(({ path, label, icon: Icon }) => {
            return (
              <li key={path}>
                <NavLink to={path} end={path === "/"} className={(s) => cn(linkClass(s), "min-h-9 px-2")}>
                  <Icon size={16} aria-hidden /> {label}
                </NavLink>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="flex min-w-0 flex-1 flex-col pb-14 md:pb-0">
        <TopBar />
        <StatusBanner />
        <main className="flex-1 p-4">
          <Outlet />
        </main>
        <Footer />
      </div>
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-10 flex border-t border-border bg-page md:hidden"
      >
        {NAV_ITEMS.map(({ path, label, icon: Icon }) => {
          return (
            <NavLink
              key={path}
              to={path}
              end={path === "/"}
              className={(s) => cn(linkClass(s), "min-h-14 flex-1 flex-col justify-center gap-0 text-caption")}
            >
              <Icon size={20} aria-hidden />
              {label}
            </NavLink>
          );
        })}
      </nav>
    </div>
  );
}
