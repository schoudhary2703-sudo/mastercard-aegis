import { useLocation } from "react-router-dom";
import { LOOP_STEPS, stepFor } from "../../nav/journey";
import { MenuIcon } from "./icons";

/**
 * Slim chrome. Page titles live on the pages themselves, so this bar carries
 * the mobile menu trigger, a "you are here" marker for the walkthrough, and
 * the data-provenance indicator.
 *
 * The step marker lets a judge who lands mid-sequence see where they are
 * without reading the sidebar. The provenance chip flips to "Simulated" on
 * the sandbox, so a screen of browser-generated numbers can never be mistaken
 * for evidence.
 *
 * The mock round counter and its reset button moved to the sandbox itself:
 * persistent chrome on every screen was the one place mock state could still
 * appear beside real artifacts.
 */
export function Topbar({ onOpenMenu }: { onOpenMenu: () => void }) {
  const { pathname } = useLocation();
  const current = stepFor(pathname);
  const isSandbox = pathname.startsWith("/sandbox");

  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-[var(--color-border)] bg-[var(--color-surface)] px-3 sm:px-5 lg:px-6">
      <div className="flex min-w-0 items-center gap-2.5">
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

        {current?.step != null && (
          <span className="hidden items-center gap-2 lg:flex">
            <span className="t-eyebrow text-[var(--color-ink-faint)]">
              Step {current.step} of {LOOP_STEPS.length} · {current.label}
            </span>
            <span className="text-[11px] text-[var(--color-ink-faint)] opacity-70">
              {current.rubric}
            </span>
          </span>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-2">
        {isSandbox ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--color-risk-medium-100)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-risk-medium-600)]">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-risk-medium-600)]" />
            Simulated
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--color-defend-100)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-defend-600)]">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-defend-600)]" />
            Real artifacts
          </span>
        )}
      </div>
    </header>
  );
}
