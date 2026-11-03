import { NavLink } from "react-router-dom";

import { cn } from "@/shared/lib/utils";

const linkClass =
  "rounded-md px-3 py-2 text-sm font-medium text-ink-muted transition hover:bg-input hover:text-ink";

const activeClass = "bg-input text-ink";

export function AppNav() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-surface/95 backdrop-blur-sm">
      <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-2 px-4 lg:px-6">
        <NavLink
          to="/"
          end
          className={({ isActive }) =>
            cn("mr-2 shrink-0 text-sm font-semibold tracking-tight text-ink", isActive && "text-accent")
          }
        >
          The Bridge
        </NavLink>
        <nav className="flex flex-1 flex-wrap items-center gap-1" aria-label="Main">
          <NavLink to="/explore" className={({ isActive }) => cn(linkClass, isActive && activeClass)}>
            Explore
          </NavLink>
          <NavLink to="/ask" className={({ isActive }) => cn(linkClass, isActive && activeClass)}>
            Ask
          </NavLink>
        </nav>
      </div>
    </header>
  );
}
