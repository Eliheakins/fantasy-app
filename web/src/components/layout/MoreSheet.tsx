import { Ellipsis, X } from "lucide-react";
import { Dialog } from "radix-ui";
import { useEffect, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { navSearch } from "./navLinks";
import { MORE_ITEMS } from "@/nav";
import { cn } from "@/lib/utils";

/** The phone tab bar's last tab: opens a Radix Dialog sheet (focus trap, Esc, labelled) listing the pages without a tab. */
export function MoreSheet({ tabClass }: { tabClass: string }) {
  const [open, setOpen] = useState(false);
  const { pathname, search } = useLocation();
  // A close caused by navigation must not pull focus back to the trigger: the page heading has it.
  const closedByNavigation = useRef(false);
  useEffect(() => {
    closedByNavigation.current = true;
    setOpen(false);
  }, [pathname]);
  const onMore = MORE_ITEMS.some((i) => i.path === pathname);
  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (next) closedByNavigation.current = false;
        setOpen(next);
      }}
    >
      <Dialog.Trigger
        className={cn(
          tabClass,
          "tab-link min-h-[56px] min-w-0 flex-1 flex-col justify-center gap-0.5",
          onMore && "bg-nav-active-bg font-semibold text-accent shadow-[inset_0_3px_0_var(--accent)]",
        )}
      >
        <Ellipsis size={20} aria-hidden />
        <span className="tab-label">More</span>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-page/70" />
        <Dialog.Content
          onCloseAutoFocus={(e) => closedByNavigation.current && e.preventDefault()}
          className="fixed inset-x-0 bottom-0 z-50 rounded-t-2xl border-x border-t border-border bg-surface p-4 pb-[max(1rem,env(safe-area-inset-bottom))] outline-hidden">
          <div className="flex items-center justify-between">
            <Dialog.Title className="text-heading font-semibold">More</Dialog.Title>
            <Dialog.Close aria-label="Close" className="flex h-11 w-11 items-center justify-center rounded-full text-text">
              <X size={20} aria-hidden />
            </Dialog.Close>
          </div>
          <Dialog.Description className="sr-only">Pages that do not have their own tab.</Dialog.Description>
          <nav aria-label="More pages">
          <ul className="mt-2 flex flex-col">
            {MORE_ITEMS.map(({ path, label, icon: Icon }) => (
              <li key={path}>
                <NavLink
                  to={{ pathname: path, search: navSearch(path, search, pathname) }}
                  onClick={() => {
                    closedByNavigation.current = true;
                    setOpen(false);
                  }}
                  className={({ isActive }) =>
                    cn("flex min-h-[44px] items-center gap-3 px-2 text-body", isActive ? "font-semibold text-accent" : "text-text")
                  }
                >
                  <Icon size={18} aria-hidden /> {label}
                </NavLink>
              </li>
            ))}
          </ul>
          </nav>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
