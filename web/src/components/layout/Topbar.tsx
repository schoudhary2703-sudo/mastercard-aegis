import { useLoop } from "../../state/LoopContext";
import { MenuIcon, ResetIcon } from "./icons";

/**
 * Slim chrome. Page titles live on the pages themselves, so this bar carries
 * the mobile menu trigger, the competition context, and the data-provenance
 * indicator. The mock-demo round counter appears only once a mock round has
 * been run, so it never sits next to real data by default.
 */
export function Topbar({ onOpenMenu }: { onOpenMenu: () => void }) {
  const { rounds, reset } = useLoop();

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
        <span className="t-eyebrow hidden truncate text-[var(--color-ink-faint)] lg:inline">
          Mastercard Innovation Challenge 2026
        </span>
      </div>

      <div className="flex shrink-0 items-center gap-2.5">
        <span className="t-mono-sm hidden text-[var(--color-ink-faint)] md:inline">
          synthetic PaySim · read-only
        </span>
        <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-defend-600)]/30 bg-[var(--color-defend-100)] px-2.5 py-1 text-[10.5px] font-medium uppercase tracking-[0.08em] text-[var(--color-defend-600)]">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-defend-600)]" />
          Real artifacts
        </span>
        {rounds.length > 0 && (
          <button
            type="button"
            onClick={reset}
            className="flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-2.5 py-1 text-[11.5px] font-medium text-[var(--color-ink-muted)] transition-standard hover:border-[var(--color-border-strong)] hover:text-[var(--color-ink)]"
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
