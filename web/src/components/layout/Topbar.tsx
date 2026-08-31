import { Link, useLocation } from "react-router-dom";
import { JOURNEY, LOOP_STEPS, nextStepFor, stepFor } from "../../nav/journey";
import { MenuIcon } from "./icons";

/**
 * Chrome, and the walkthrough's permanent controls.
 *
 * The bar carries prev/next for the numbered path. That is the fix for the
 * real navigation complaint: without it, moving to the next screen means
 * scrolling to the bottom of a three-screen page or going back to the
 * sidebar. With it, the whole walkthrough is reachable from a fixed position
 * no matter how far down the reader is.
 *
 * A step marker shows position in the sequence, and the provenance chip flips
 * to "Simulated" on the sandbox so a screen of browser-generated numbers can
 * never be mistaken for evidence.
 */
export function Topbar({ onOpenMenu }: { onOpenMenu: () => void }) {
  const { pathname } = useLocation();
  const current = stepFor(pathname);
  const next = nextStepFor(pathname);
  const isSandbox = pathname.startsWith("/sandbox");

  const index = current ? JOURNEY.indexOf(current) : -1;
  const prev = index > 0 ? JOURNEY[index - 1] : null;

  return (
    <header className="z-20 flex h-14 shrink-0 items-center justify-between gap-3 border-b border-[var(--color-border)] bg-[var(--color-surface)]/95 px-4 backdrop-blur sm:px-6 lg:px-8">
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
          <span className="hidden min-w-0 items-baseline gap-2.5 lg:flex">
            <span className="t-eyebrow shrink-0 text-[var(--color-accent-600)]">
              Step {current.step}/{LOOP_STEPS.length}
            </span>
            <span className="t-h2 truncate text-[var(--color-ink)]">{current.label}</span>
            <span className="t-body-sm truncate text-[var(--color-ink-faint)]">
              {current.rubric}
            </span>
          </span>
        ) : (
          current && (
            <span className="hidden min-w-0 items-baseline gap-2.5 lg:flex">
              <span className="t-h2 truncate text-[var(--color-ink)]">{current.label}</span>
              <span className="t-body-sm truncate text-[var(--color-ink-faint)]">
                {current.rubric}
              </span>
            </span>
          )
        )}
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <span
          className={`hidden items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide sm:inline-flex ${
            isSandbox
              ? "bg-[var(--color-risk-medium-100)] text-[var(--color-risk-medium-600)]"
              : "bg-[var(--color-defend-100)] text-[var(--color-defend-600)]"
          }`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              isSandbox
                ? "bg-[var(--color-risk-medium-600)]"
                : "bg-[var(--color-defend-600)]"
            }`}
          />
          {isSandbox ? "Simulated" : "Real artifacts"}
        </span>

        {/* Permanent step controls: the walkthrough is navigable from any
            scroll position, on any screen. */}
        {(prev || next) && (
          <div className="flex items-center overflow-hidden rounded-lg border border-[var(--color-border)]">
            {prev ? (
              <Link
                to={prev.to}
                aria-label={`Previous: ${prev.label}`}
                title={`Previous: ${prev.label}`}
                className="px-2.5 py-1.5 text-[var(--color-ink-muted)] transition-standard hover:bg-[var(--color-surface-sunken)] hover:text-[var(--color-ink)]"
              >
                <span aria-hidden="true">←</span>
              </Link>
            ) : (
              <span className="px-2.5 py-1.5 text-[var(--color-border-strong)]" aria-hidden="true">
                ←
              </span>
            )}
            {next ? (
              <Link
                to={next.to}
                className="flex items-center gap-1.5 border-l border-[var(--color-border)] px-3 py-1.5 text-[12.5px] font-medium text-[var(--color-ink)] transition-standard hover:bg-[var(--color-surface-sunken)]"
              >
                <span className="hidden md:inline">{next.label}</span>
                <span aria-hidden="true">→</span>
              </Link>
            ) : (
              <span
                className="border-l border-[var(--color-border)] px-2.5 py-1.5 text-[var(--color-border-strong)]"
                aria-hidden="true"
              >
                →
              </span>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
