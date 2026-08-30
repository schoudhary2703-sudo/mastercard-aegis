import { useLocation } from "react-router-dom";
import { LOOP_STEPS, stepFor } from "../../nav/journey";
import { MenuIcon } from "./icons";

/**
 * Slim chrome. Page titles live on the pages themselves, so this bar carries
 * the mobile menu trigger, a "you are here" marker for the walkthrough, and
 * the data-provenance indicator.
 *
 * The step marker replaces the old static competition line: a judge landing
 * mid-sequence can see where they are without reading the sidebar, and the
 * sandbox is called out explicitly so simulated screens can never be mistaken
 * for evidence.
 */
export function Topbar({ onOpenMenu }: { onOpenMenu: () => void }) {
  const { pathname } = useLocation();
  const current = stepFor(pathname);
  const isSandbox = pathname.startsWith("/sandbox");

  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-[var(--color-border)] bg-[var(--color-canvas)]/80 px-4 backdrop-blur sm:px-7 lg:px-10">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={onOpenMenu}
          aria-label="Open navigation"
          className="rounded-lg border border-[var(--color-border)] p-1.5 text-[var(--color-ink-muted)] transition-standard hover:text-[var(--color-ink)] lg:hidden"
        >
          <MenuIcon />
        </button>
        <span className="truncate text-sm font-semibold text-[var(--color-ink)] lg:hidden">
          AEGIS
        </span>

        {current?.step != null ? (
          <span className="hidden items-center gap-2 lg:flex">
            <span className="t-eyebrow text-[var(--color-ink-faint)]">
              Step {current.step} of {LOOP_STEPS.length} · {current.label}
            </span>
            <span className="text-[11px] text-[var(--color-ink-faint)] opacity-70">
              {current.rubric}
            </span>
          </span>
        ) : (
          <span className="t-eyebrow hidden truncate text-[var(--color-ink-faint)] lg:inline">
            Mastercard Innovation Challenge 2026
          </span>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-2.5">
        <span className="t-mono-sm hidden text-[var(--color-ink-faint)] md:inline">
          synthetic PaySim · read-only
        </span>
        {isSandbox ? (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-risk-medium-600)]/30 bg-[var(--color-risk-medium-100)] px-2.5 py-1 text-[10.5px] font-medium uppercase tracking-[0.08em] text-[var(--color-risk-medium-600)]">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-risk-medium-600)]" />
            Simulated
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-defend-600)]/30 bg-[var(--color-defend-100)] px-2.5 py-1 text-[10.5px] font-medium uppercase tracking-[0.08em] text-[var(--color-defend-600)]">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-defend-600)]" />
            Real artifacts
          </span>
        )}
      </div>
    </header>
  );
}
