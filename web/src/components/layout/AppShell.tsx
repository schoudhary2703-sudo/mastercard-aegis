import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { Sidebar, SidebarNav } from "./Sidebar";
import { Topbar } from "./Topbar";

/**
 * Shell. Below `lg` the sidebar collapses into a drawer so the core judge
 * flow is usable at 375px without shrinking type; the drawer closes on
 * navigation so a tap never leaves it covering the content it just loaded.
 */
export function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();

  useEffect(() => setMenuOpen(false), [location.pathname]);

  return (
    <div className="flex h-screen w-full overflow-hidden">
      <Sidebar />

      {menuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            onClick={() => setMenuOpen(false)}
            className="absolute inset-0 bg-black/60"
          />
          <div className="absolute left-0 top-0 h-full w-64 overflow-y-auto bg-[var(--color-navy-950)] py-5">
            <p className="px-6 pb-4 text-sm font-semibold text-white">AEGIS</p>
            <SidebarNav onNavigate={() => setMenuOpen(false)} />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onOpenMenu={() => setMenuOpen(true)} />
        <main className="flex-1 overflow-y-auto px-4 py-7 sm:px-7 lg:px-10 lg:py-10">
          <div className="mx-auto max-w-[1200px]">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
