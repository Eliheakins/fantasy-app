import { Outlet } from "react-router-dom";

import { AppNav } from "@/app/AppNav";

export function RootLayout() {
  return (
    <div className="relative flex min-h-dvh flex-col bg-app text-ink">
      <AppNav />
      <div className="flex min-h-0 flex-1 flex-col">
        <Outlet />
      </div>
    </div>
  );
}
