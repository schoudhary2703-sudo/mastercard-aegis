import { useEffect, useRef, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { NextStep } from "./NextStep";
import { Sidebar, SidebarNav } from "./Sidebar";
import { Topbar } from "./Topbar";

/**
 * Shell.
 *
 * Below `lg` the sidebar collapses into a drawer so the core flow is usable
 * at 375px without shrinking type; the drawer closes on navigation so a tap
 * never leaves it covering the content it just loaded.
 *
 * The scroll container resets to the top on every route change. Without it,
 * arriving at a screen from the step footer at the bottom of the previous one
 * drops the reader two screens down the new page, which reads as a broken
 * link -- the single worst navigation bug a walkthrough can have.
 */
export function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  const scrollRef = useRef<HTMLElement>(null);

  useEffect(() => setMenuOpen(false), [location.pathname]);
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: 0, behavior: "auto" });
  }, [location.pathname]);

  return (
    <div className="flex h-screen w-full overflow-hidden bg-[var(--color-canvas)]">
      <Sidebar />

      {menuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            onClick={() => setMenuOpen(false)}
            className="absolute inset-0 bg-black/40"
          />
          <div className="absolute left-0 top-0 h-full w-60 overflow-y-auto bg-[var(--color-navy-950)] py-5">
            <p className="px-5 pb-4 text-sm font-semibold text-white">AEGIS</p>
            <SidebarNav onNavigate={() => setMenuOpen(false)} />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onOpenMenu={() => setMenuOpen(true)} />
        <main
          ref={scrollRef}
          className="flex-1 overflow-y-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8"
        >
          <div className="mx-auto max-w-[1180px]">
            <Outlet />
            {/* The walkthrough drives itself: one correct next screen, always
                directly under the content the reader just finished. */}
            <div className="mt-14 pb-4">
              <NextStep />
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
