import { useLoop } from "../../state/LoopContext";
import { MenuIcon, ResetIcon } from "./icons";

/**
 * Slim chrome. Page titles live on the pages themselves now, so this bar
 * carries only the mobile menu trigger, the brand, and the data-provenance
 * indicator. The mock-demo round counter appears only once a mock round has
 * actually been run, so it never sits next to real data by default.
 */
export function Topbar({ onOpenMenu }: { onOpenMenu: () => void }) {
  const { rounds, reset } = useLoop();

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
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--color-defend-100)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-defend-600)]">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-defend-600)]" />
          Real artifacts
        </span>
        {rounds.length > 0 && (
          <button
            type="button"
            onClick={reset}
            className="flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-2.5 py-1 text-[11px] font-medium text-[var(--color-ink-muted)] transition-standard hover:border-[var(--color-border-strong)] hover:text-[var(--color-ink)]"
          >
            <ResetIcon />
            <span className="hidden sm:inline">Reset demo ({rounds.length})</span>
            <span className="sm:hidden">{rounds.length}</span>
          </button>
        )}
      </div>
    </header>
  );
}
