import { useLocation } from "react-router-dom";
import { useLoop } from "../../state/LoopContext";
import { ResetIcon } from "./icons";

const TITLES: Record<string, { title: string; subtitle: string }> = {
  "/": { title: "Overview", subtitle: "System health and the closed loop at a glance." },
  "/attack-studio": { title: "Attack Studio", subtitle: "Select a family and generate a synthetic attack batch." },
  "/live-detection": { title: "Live Detection", subtitle: "Detector output per transaction, caught vs. evaded." },
  "/co-evolution": { title: "Co-Evolution", subtitle: "Run rounds and watch attack and defense adapt to each other." },
  "/attack-taxonomy": { title: "Attack Taxonomy", subtitle: "The three in-scope attack families and their blueprints." },
  "/evaluation": { title: "Evaluation", subtitle: "Protocol-scoped performance for the current round." },
};

export function Topbar() {
  const location = useLocation();
  const { rounds, reset } = useLoop();
  const meta = TITLES[location.pathname] ?? { title: "AEGIS", subtitle: "" };

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface)] px-6">
      <div>
        <h1 className="text-base font-semibold text-[var(--color-ink)]">{meta.title}</h1>
        <p className="text-xs text-[var(--color-ink-muted)]">{meta.subtitle}</p>
      </div>
      <div className="flex items-center gap-3">
        <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-surface-sunken)] px-3 py-1 text-xs font-medium text-[var(--color-ink-muted)]">
          Round {rounds.length} · Mock data
        </span>
        <button
          type="button"
          onClick={reset}
          className="flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium text-[var(--color-ink-muted)] transition-standard hover:border-[var(--color-border-strong)] hover:text-[var(--color-ink)]"
        >
          <ResetIcon />
          Reset demo
        </button>
      </div>
    </header>
  );
}
